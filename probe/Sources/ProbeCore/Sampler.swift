import Foundation
import os

/// Posts a query's keys on a fixed schedule that nothing the sampler does can delay.
public protocol KeyPacer: AnyObject {
    /// Starts posting `characters[i]` at `startMs + i * intervalMs` and returns at once.
    func begin(_ characters: [String], startMs: Int, intervalMs: Int)
    /// The keys posted so far, in order, with times relative to `startMs`.
    func posted() -> [KeyPostDTO]
}

/// Paces keys from its own thread, so a slow accessibility read on the sampling thread cannot
/// hold a key back.
public final class ThreadKeyPacer: KeyPacer {
    private let keys: any KeyPoster & Sendable
    private let clock: any ProbeClock & Sendable
    private let log = OSAllocatedUnfairLock(initialState: [KeyPostDTO]())

    public init(keys: any KeyPoster & Sendable, clock: any ProbeClock & Sendable) {
        self.keys = keys
        self.clock = clock
    }

    public func begin(_ characters: [String], startMs: Int, intervalMs: Int) {
        let thread = Thread { [keys, clock, log] in
            if !ThreadKeyPacer.makeCurrentThreadRealTime() {
                FileHandle.standardError.write(Data("key pacer: no real-time scheduling\n".utf8))
            }
            for (i, character) in characters.enumerated() {
                let planned = i * intervalMs
                clock.sleep(untilMs: startMs + planned)
                let actual = clock.nowMs() - startMs
                keys.type(character)
                log.withLock { $0.append(KeyPostDTO(plannedMs: planned, actualMs: actual)) }
            }
        }
        thread.start()
    }

    public func posted() -> [KeyPostDTO] { log.withLock { $0 } }

    /// Ordinary threads wake up to 10 ms late from a timed sleep (timer coalescing); a
    /// time-constraint thread wakes within about 0.05 ms.
    private static func makeCurrentThreadRealTime() -> Bool {
        var timebase = mach_timebase_info_data_t()
        guard mach_timebase_info(&timebase) == KERN_SUCCESS, timebase.numer > 0 else { return false }
        func ticks(ms: Int) -> UInt32 {
            UInt32(ms * 1_000_000 * Int(timebase.denom) / Int(timebase.numer))
        }
        var policy = thread_time_constraint_policy_data_t(
            period: ticks(ms: 80), computation: ticks(ms: 1), constraint: ticks(ms: 2),
            preemptible: 1)
        let count = mach_msg_type_number_t(
            MemoryLayout<thread_time_constraint_policy_data_t>.size / MemoryLayout<integer_t>.size)
        return withUnsafeMutablePointer(to: &policy) {
            $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                thread_policy_set(pthread_mach_thread_np(pthread_self()),
                                  thread_policy_flavor_t(THREAD_TIME_CONSTRAINT_POLICY), $0, count)
            }
        } == KERN_SUCCESS
    }
}

/// Types a query at a fixed pace and samples the launcher's rows about every 50 ms until the
/// observation window after the final key has passed. Never stops early.
public final class Sampler {
    public static let sampleIntervalMs = 50
    /// A key posted later than this makes the sample a harness error. 10 ms is an eighth of the
    /// 80 ms key interval and a tenth of the earliest checkpoint.
    public static let maxKeyLatenessMs = 10
    /// One whole read (field, rows, Enter label) must finish within this, or it is unreadable.
    public static let readBudgetMs = 150

    let adapter: LauncherAdapter
    let pacer: KeyPacer
    let clock: ProbeClock

    public init(adapter: LauncherAdapter, pacer: KeyPacer, clock: ProbeClock) {
        self.adapter = adapter
        self.pacer = pacer
        self.clock = clock
    }

    public func run(text: String, mode: TypingMode, windowMs: Int) -> SampleDTO {
        guard adapter.isReady() else {
            return SampleDTO(keyPosts: [], fieldShowsMs: nil, snapshots: [], error: "not_ready")
        }
        let characters = text.map(String.init)
        let plannedFinalKey = max(characters.count - 1, 0) * mode.keyIntervalMs
        let start = clock.nowMs()
        pacer.begin(characters, startMs: start, intervalMs: mode.keyIntervalMs)

        var sample = SampleDTO(keyPosts: [], fieldShowsMs: nil, snapshots: [], error: nil)
        var nextSample = 0
        var readFailures = 0
        var allPosted = false
        repeat {
            clock.sleep(untilMs: start + nextSample)
            let postedBeforeRead = pacer.posted().count
            let readStart = clock.nowMs() - start
            ReadBudget.shared.begin(ms: Sampler.readBudgetMs, clock: clock)
            let read = adapter.fieldText()
            let fieldRead = clock.nowMs() - start
            let postedAfterRead = pacer.posted().count
            var rows: Result<([RowDTO], String?), any Error>?
            if case .text(let field) = read, !field.isEmpty,
               characters.prefix(postedAfterRead).joined().hasPrefix(field) {
                rows = Result { (try adapter.readRows(), adapter.primaryAction()) }
            }
            let overBudget = ReadBudget.shared.end()
            let readEnd = clock.nowMs() - start
            if overBudget {
                if postedBeforeRead > 0 {
                    readFailures += 1
                    sample.snapshots.append(
                        SnapshotDTO(readStartMs: readStart, readEndMs: readEnd, rows: [],
                                    fieldText: "", unreadable: "deadline"))
                }
                sample.keyPosts = pacer.posted()
                allPosted = sample.keyPosts.count == characters.count
                nextSample = max(nextSample + Sampler.sampleIntervalMs, clock.nowMs() - start)
                continue
            }
            guard case .text(let field) = read else {
                if postedBeforeRead > 0, case .unreadable(let reason) = read {
                    readFailures += 1
                    sample.snapshots.append(
                        SnapshotDTO(readStartMs: readStart, readEndMs: fieldRead, rows: [],
                                    fieldText: "", unreadable: "field:\(reason)"))
                }
                sample.keyPosts = pacer.posted()
                allPosted = sample.keyPosts.count == characters.count
                nextSample = max(nextSample + Sampler.sampleIntervalMs, clock.nowMs() - start)
                continue
            }
            if field == text && postedAfterRead == characters.count && sample.fieldShowsMs == nil {
                sample.fieldShowsMs = fieldRead
            }
            // Keep rows whenever the field shows some prefix of what was typed: a lagging field
            // is exactly what Enter would act on. Drop only rows from before the new text appears.
            if field.isEmpty && postedBeforeRead > 0 {
                // Typed but not yet shown: Enter would open nothing from this query.
                sample.snapshots.append(
                    SnapshotDTO(readStartMs: readStart, readEndMs: fieldRead, rows: [], fieldText: ""))
            } else if let rows {
                switch rows {
                case .success(let (found, action)):
                    sample.snapshots.append(
                        SnapshotDTO(readStartMs: readStart, readEndMs: readEnd,
                                    rows: found, fieldText: field, primaryAction: action))
                case .failure(let error):
                    readFailures += 1
                    sample.snapshots.append(
                        SnapshotDTO(readStartMs: readStart, readEndMs: readEnd,
                                    rows: [], fieldText: field, unreadable: "rows:\(error)"))
                }
            } else if !field.isEmpty {
                sample.snapshots.append(
                    SnapshotDTO(readStartMs: readStart, readEndMs: fieldRead, rows: [],
                                fieldText: field, fieldMismatch: true))
            }
            sample.keyPosts = pacer.posted()
            allPosted = sample.keyPosts.count == characters.count
            nextSample = max(nextSample + Sampler.sampleIntervalMs, clock.nowMs() - start)
        } while nextSample <= (allPosted ? sample.finalKeyPostMs : plannedFinalKey) + windowMs

        if !allPosted {
            sample.error = "keys_not_posted"
        } else if !sample.snapshots.contains(where: {
            !$0.fieldText.isEmpty && !$0.fieldMismatch && $0.unreadable == nil
        }) {
            sample.error = readFailures > 0 ? "ax_read_failed" : "field_never_matched"
        } else if sample.maxKeyLatenessMs > Sampler.maxKeyLatenessMs {
            sample.error = "key_post_late"
        }
        return sample
    }
}
