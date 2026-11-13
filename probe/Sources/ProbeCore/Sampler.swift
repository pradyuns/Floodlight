/// Types a query at a fixed pace and samples the launcher's rows every 50 ms until the
/// observation window after the final key has passed. Never stops early.
public final class Sampler {
    public static let sampleIntervalMs = 50

    let adapter: LauncherAdapter
    let keys: KeyPoster
    let clock: ProbeClock

    public init(adapter: LauncherAdapter, keys: KeyPoster, clock: ProbeClock) {
        self.adapter = adapter
        self.keys = keys
        self.clock = clock
    }

    public func run(text: String, mode: TypingMode, windowMs: Int) -> SampleDTO {
        guard adapter.isReady() else {
            return SampleDTO(finalKeyPostMs: 0, fieldShowsMs: nil, snapshots: [], error: "not_ready")
        }
        let characters = text.map(String.init)
        let keyTimes = characters.indices.map { $0 * mode.keyIntervalMs }
        let finalKey = keyTimes.last ?? 0
        let end = finalKey + windowMs
        let start = clock.nowMs()

        var sample = SampleDTO(finalKeyPostMs: finalKey, fieldShowsMs: nil, snapshots: [], error: nil)
        var nextKey = 0
        var nextSample = 0
        var readFailures = 0
        while nextSample <= end {
            if nextKey < characters.count && keyTimes[nextKey] <= nextSample {
                clock.sleep(untilMs: start + keyTimes[nextKey])
                keys.type(characters[nextKey])
                nextKey += 1
                continue
            }
            clock.sleep(untilMs: start + nextSample)
            let t = clock.nowMs() - start
            let expected = characters.prefix(nextKey).joined()
            let field = adapter.fieldText() ?? ""
            if field == text && nextKey == characters.count && sample.fieldShowsMs == nil {
                sample.fieldShowsMs = t
            }
            // Keep rows whenever the field shows some prefix of what was typed: a lagging field
            // is exactly what Enter would act on. Drop only rows from before the new text appears.
            if field.isEmpty && nextKey > 0 {
                // Typed but not yet shown: Enter would open nothing from this query.
                sample.snapshots.append(SnapshotDTO(tMs: t, rows: [], fieldText: ""))
            } else if !field.isEmpty && expected.hasPrefix(field) {
                do {
                    sample.snapshots.append(
                        SnapshotDTO(tMs: t, rows: try adapter.readRows(), fieldText: field))
                } catch {
                    readFailures += 1
                }
            }
            nextSample += Sampler.sampleIntervalMs
        }
        if !sample.snapshots.contains(where: { !$0.fieldText.isEmpty }) {
            sample.error = readFailures > 0 ? "ax_read_failed" : "field_never_matched"
        }
        return sample
    }
}
