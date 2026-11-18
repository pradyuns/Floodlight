/// Ends a launcher's UI process and waits for a new one.
public struct UIRestart {
    let pids: () -> Set<Int32>
    let terminate: () -> Void
    /// nil: the launcher relaunches itself.
    let relaunch: (() -> Void)?
    let waitUntil: (Int, () -> Bool) -> Bool

    public init(pids: @escaping () -> Set<Int32>, terminate: @escaping () -> Void,
                relaunch: (() -> Void)?, waitUntil: @escaping (Int, () -> Bool) -> Bool) {
        self.pids = pids
        self.terminate = terminate
        self.relaunch = relaunch
        self.waitUntil = waitUntil
    }

    /// The old process must exit before any relaunch (a relaunch sent to an exiting app is lost),
    /// and only a process that wasn't running before counts as the new one.
    public func run(timeoutMs: Int) -> Bool {
        let old = pids()
        terminate()
        guard waitUntil(timeoutMs, { pids().isDisjoint(with: old) }) else { return false }
        relaunch?()
        return waitUntil(timeoutMs) { !pids().subtracting(old).isEmpty }
    }
}
