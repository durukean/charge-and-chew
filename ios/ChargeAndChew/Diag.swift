import Foundation

/// Appends to a file in the app container.
///
/// NSLog and print both proved unreadable from outside the simulator here, which turned a
/// blank-screen bug into guesswork. A file in Documents can be read straight off disk with
/// `simctl get_app_container`, so boot problems are diagnosable without a debugger attached.
enum Diag {
    private static let url: URL = {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("cc-boot.log")
    }()

    static func reset() { try? "".write(to: url, atomically: true, encoding: .utf8) }

    static func log(_ message: String) {
        #if !DEBUG
        return                      // a release build has no business writing a boot log
        #endif
        let line = "\(Date().timeIntervalSince1970) \(message)\n"
        NSLog("[cc] %@", message)
        guard let data = line.data(using: .utf8) else { return }
        if let h = try? FileHandle(forWritingTo: url) {
            defer { try? h.close() }
            h.seekToEndOfFile()
            h.write(data)
        } else {
            try? data.write(to: url)
        }
    }
}
