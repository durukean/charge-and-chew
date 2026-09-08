import Foundation
import WebKit

/// Serves the bundled web app to WKWebView under `chargeandchew://app/…`.
///
/// This replaced a loopback HTTP server. That worked, but the origin of a page includes its
/// port, and web storage is per-origin: when the fixed port was ever taken -- two simulators
/// on one Mac was enough -- the server fell back to a random port, the origin changed, and
/// favourites, the saved car and every preference silently vanished. A URL scheme handler
/// has no port and no socket: the origin is `chargeandchew://app` for the life of the
/// install, and nothing is listening on the network at all.
///
/// Custom schemes are not "secure contexts", but nothing here needs one: the service worker
/// is skipped in the shell, geolocation and sharing are bridged natively, and every remote
/// request the page makes is plain HTTPS fetch.
final class AppSchemeHandler: NSObject, WKURLSchemeHandler {

    static let scheme = "chargeandchew"
    static let origin = "chargeandchew://app"

    private let root: URL
    /// Checked before the bundle, so a data.js refreshed after install wins over the copy
    /// that shipped with the binary without the bundle itself having to be writable.
    var overlay: URL?

    init(root: URL) { self.root = root }

    func webView(_ webView: WKWebView, start task: WKURLSchemeTask) {
        guard let url = task.request.url else { return }
        var path = url.path.removingPercentEncoding ?? url.path
        if path.isEmpty || path == "/" || path.hasSuffix("/") { path += path.hasSuffix("/") ? "index.html" : "/index.html" }

        guard let file = resolve(path, in: overlay) ?? resolve(path, in: root),
              let body = try? Data(contentsOf: file) else {
            task.didReceive(HTTPURLResponse(url: url, statusCode: 404, httpVersion: "HTTP/1.1", headerFields: nil)!)
            task.didFinish()
            return
        }
        let headers = ["Content-Type": Self.mime(for: file.pathExtension),
                       "Content-Length": String(body.count),
                       "Cache-Control": "no-store"]          // the bundle IS the cache
        task.didReceive(HTTPURLResponse(url: url, statusCode: 200, httpVersion: "HTTP/1.1", headerFields: headers)!)
        task.didReceive(body)
        task.didFinish()
    }

    func webView(_ webView: WKWebView, stop task: WKURLSchemeTask) {}

    /// Resolves inside `dir` only. `standardized` collapses any `..` BEFORE the prefix test,
    /// so a crafted path cannot climb out of the bundle and read arbitrary app files.
    private func resolve(_ path: String, in dir: URL?) -> URL? {
        guard let dir else { return nil }
        let url = dir.appendingPathComponent(path).standardizedFileURL
        let base = dir.standardizedFileURL.path
        guard url.path == base || url.path.hasPrefix(base + "/") else { return nil }
        var isDir: ObjCBool = false
        guard FileManager.default.fileExists(atPath: url.path, isDirectory: &isDir), !isDir.boolValue else { return nil }
        return url
    }

    private static func mime(for ext: String) -> String {
        switch ext.lowercased() {
        case "html", "htm": return "text/html; charset=utf-8"
        case "js", "mjs":   return "text/javascript; charset=utf-8"
        case "css":         return "text/css; charset=utf-8"
        case "json":        return "application/json; charset=utf-8"
        case "webmanifest": return "application/manifest+json"
        case "svg":         return "image/svg+xml"
        case "png":         return "image/png"
        case "jpg", "jpeg": return "image/jpeg"
        case "webp":        return "image/webp"
        case "ico":         return "image/x-icon"
        case "woff2":       return "font/woff2"
        default:            return "application/octet-stream"
        }
    }
}
