import Foundation

/// Keeps the bundled charger data fresh without an App Store release.
///
/// data.js ships inside the binary so the very first launch works with no signal at all --
/// that offline-first behaviour is the point of the app, not a fallback. But the dataset is
/// rebuilt monthly, and shipping a new binary for it would leave every user who has not
/// updated looking at stale chargers. So on launch we quietly ask the site whether it has a
/// newer build and, if so, drop it in an overlay directory the local server checks first.
///
/// Failure is silent and total: any error at any step leaves the bundled copy in place. An
/// app that works offline must never be *worse* off for having tried the network.
enum DataUpdater {

    private static let remote = URL(string: "https://chargeandchew.com/data.js")!
    private static let generatedKey = "cc.data.generated"

    static var overlayDir: URL {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        return base.appendingPathComponent("web", isDirectory: true)
    }

    /// The `generated` date of whatever the server should be compared against -- the
    /// downloaded copy if we have one, otherwise the copy inside the bundle.
    static func currentGenerated(bundled: URL?) -> String {
        if let saved = UserDefaults.standard.string(forKey: generatedKey),
           FileManager.default.fileExists(atPath: overlayDir.appendingPathComponent("data.js").path) {
            return saved
        }
        return bundled.flatMap { generatedDate(in: $0) } ?? ""
    }

    /// Reads only the head of the file: the marker is in the first 40 bytes and these are
    /// multi-megabyte files that have no business being loaded into memory to read a date.
    private static func generatedDate(in file: URL) -> String? {
        guard let handle = try? FileHandle(forReadingFrom: file) else { return nil }
        defer { try? handle.close() }
        guard let head = try? handle.read(upToCount: 512) else { return nil }
        return generatedDate(inHead: String(decoding: head, as: UTF8.self))
    }

    private static func generatedDate(inHead head: String) -> String? {
        guard let r = head.range(of: #""generated":"[0-9-]+""#, options: .regularExpression) else { return nil }
        return String(head[r]).split(separator: "\"").last.map(String.init)
    }

    /// An app update can ship data NEWER than a copy downloaded earlier. Every reader --
    /// the web view, the native charger store and the Siri intent -- prefers the overlay
    /// unconditionally, so without this a stale download would keep winning over a fresher
    /// bundle for good: `currentGenerated` stops consulting the bundle once an overlay exists,
    /// so it never even noticed. Worse, it pairs the update's new index.html (served from the
    /// bundle) with old-format data.js (served from the overlay) -- the day an update changes
    /// the data format, that pairing breaks.
    /// Drop the overlay whenever the bundle is at least as new. Reads the date from the FILE,
    /// not UserDefaults, so a lost or mismatched preference cannot keep a stale copy alive.
    /// Cheap and idempotent: 512 bytes from each file.
    static func pruneStaleOverlay(bundled: URL?) {
        let file = overlayDir.appendingPathComponent("data.js")
        guard FileManager.default.fileExists(atPath: file.path) else { return }
        let overlayDate = generatedDate(in: file) ?? ""
        let bundleDate = bundled.flatMap { generatedDate(in: $0) } ?? ""
        // An unreadable overlay (no date) is treated as older than anything -- also dropped.
        guard bundleDate >= overlayDate else { return }
        try? FileManager.default.removeItem(at: file)
        UserDefaults.standard.removeObject(forKey: generatedKey)
        Diag.log("dropped stale data overlay (\(overlayDate.isEmpty ? "undated" : overlayDate)) -- bundle is \(bundleDate)")
    }

    /// The data shape a file declares (`"fmt":N` in its head). Files from before the field
    /// existed are format 1. Mirrors DATA_FMT in index.html and data/build_data.py.
    static func format(inHead head: String) -> Int {
        guard let r = head.range(of: #""fmt":[0-9]+"#, options: .regularExpression),
              let n = Int(head[r].split(separator: ":").last ?? "") else { return 1 }
        return n
    }

    private static func head(of file: URL) -> String? {
        guard let handle = try? FileHandle(forReadingFrom: file) else { return nil }
        defer { try? handle.close() }
        return (try? handle.read(upToCount: 512)).map { String(decoding: $0, as: UTF8.self) }
    }

    /// Smallest dataset accepted from the network. The real one has ~14,000 sites; a file
    /// with a fraction of that is a broken build, not a quiet month.
    private static let minSites = 5_000

    /// Removes the downloaded copy so every reader falls back to the bundled data. Called
    /// when the page reports that the data it was served would not load.
    @discardableResult
    static func discardOverlay(reason: String) -> Bool {
        let file = overlayDir.appendingPathComponent("data.js")
        guard FileManager.default.fileExists(atPath: file.path) else { return false }
        try? FileManager.default.removeItem(at: file)
        UserDefaults.standard.removeObject(forKey: generatedKey)
        Diag.log("discarded data overlay: \(reason)")
        return true
    }

    static func refresh(bundled: URL?, completion: @escaping (Bool) -> Void) {
        let have = currentGenerated(bundled: bundled)
        // The format this build's bundled page reads. A download in any other shape would
        // break it, so it is never kept, however new.
        let wantFmt = bundled.flatMap { head(of: $0) }.map { format(inHead: $0) } ?? 1

        // Step 1: only the first 512 bytes. The server honours Range, so a launch with
        // nothing new costs half a kilobyte instead of the whole 1 MB dataset.
        var probe = URLRequest(url: remote)
        probe.timeoutInterval = 15
        probe.cachePolicy = .reloadIgnoringLocalCacheData
        probe.setValue("bytes=0-511", forHTTPHeaderField: "Range")
        URLSession.shared.dataTask(with: probe) { data, response, _ in
            guard let data, let http = response as? HTTPURLResponse,
                  http.statusCode == 206 || http.statusCode == 200 else { return completion(false) }
            let h = String(decoding: data.prefix(512), as: UTF8.self)
            guard let fresh = generatedDate(inHead: h), fresh > have,
                  format(inHead: h) == wantFmt else { return completion(false) }
            download(expecting: fresh, fmt: wantFmt, completion: completion)
        }.resume()
    }

    /// Step 2: the full file, validated end to end before it may replace anything.
    private static func download(expecting fresh: String, fmt: Int, completion: @escaping (Bool) -> Void) {
        var req = URLRequest(url: remote)
        req.timeoutInterval = 30
        req.cachePolicy = .reloadIgnoringLocalCacheData
        URLSession.shared.dataTask(with: req) { data, response, _ in
            guard let data,
                  let http = response as? HTTPURLResponse, http.statusCode == 200,
                  data.count > 100_000                              // never overwrite with a error page
            else { return completion(false) }

            let h = String(decoding: data.prefix(512), as: UTF8.self)
            guard generatedDate(inHead: h) == fresh, format(inHead: h) == fmt else { return completion(false) }
            /* Size, status and date said nothing about whether the file was COMPLETE. A
               truncated download that passed them became the copy every later launch read,
               and the app opened to a red error screen for good -- reproduced in the
               simulator. Decode it exactly as the app will before it may replace anything. */
            guard let root = ChargerStore.decodePayload(String(decoding: data, as: UTF8.self)),
                  let sites = root["sites"] as? [Any], sites.count >= minSites,
                  root["matches"] is [String: Any], root["brands"] is [String: Any]
            else {
                Diag.log("rejected downloaded data.js: incomplete or malformed")
                return completion(false)
            }

            do {
                try FileManager.default.createDirectory(at: overlayDir, withIntermediateDirectories: true)
                // Re-downloadable, so keep it out of the user's iCloud backup.
                var dir = overlayDir
                var rv = URLResourceValues(); rv.isExcludedFromBackup = true
                try? dir.setResourceValues(rv)
                let tmp = overlayDir.appendingPathComponent("data.js.tmp")
                let dest = overlayDir.appendingPathComponent("data.js")
                // Write then move: a half-written data.js served on the next launch would
                // break the app in a way no reinstall-free path could recover from.
                try data.write(to: tmp, options: .atomic)
                _ = try? FileManager.default.removeItem(at: dest)
                try FileManager.default.moveItem(at: tmp, to: dest)
                UserDefaults.standard.set(fresh, forKey: generatedKey)
                completion(true)
            } catch {
                completion(false)
            }
        }.resume()
    }
}
