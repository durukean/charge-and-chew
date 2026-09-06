import Foundation
import Network

/// A tiny static file server bound to the loopback interface.
///
/// The bundled web app is NOT loaded over `file://`. A file URL is not a "potentially
/// trustworthy origin", so on that scheme WebKit disables service workers, gives every
/// document an opaque origin that breaks `localStorage`, and refuses `fetch` between
/// bundled files. `http://127.0.0.1` *is* trustworthy by definition, so serving our own
/// bundle over loopback gets the whole platform back without shipping anything remote.
///
/// Nothing leaves the device: the listener is pinned to loopback and the port is random per
/// launch, so no other process can guess it and the app answers no request from the network.
final class LocalServer {

    private var listener: NWListener?
    private let root: URL
    /// Checked before the bundle, so a data.js refreshed after install wins over the copy
    /// that shipped with the binary without the bundle itself having to be writable.
    var overlay: URL?
    private let queue = DispatchQueue(label: "cc.localserver", attributes: .concurrent)

    private(set) var port: UInt16 = 0

    init(root: URL) { self.root = root }

    /// Starts on a random free loopback port and returns once it is actually listening, so
    /// the caller can load a URL immediately without racing the socket.
    func start() throws -> UInt16 {
        let params = NWParameters.tcp
        params.requiredInterfaceType = .loopback
        params.allowLocalEndpointReuse = true

        let listener = try NWListener(using: params, on: .any)
        self.listener = listener

        let ready = DispatchSemaphore(value: 0)
        var startError: Error?

        listener.stateUpdateHandler = { [weak self] state in
            switch state {
            case .ready:
                self?.port = listener.port?.rawValue ?? 0
                ready.signal()
            case .failed(let e), .waiting(let e):
                startError = e
                ready.signal()
            default:
                break
            }
        }
        listener.newConnectionHandler = { [weak self] conn in
            conn.start(queue: self?.queue ?? .global())
            self?.receive(on: conn, buffer: Data())
        }
        listener.start(queue: queue)

        if ready.wait(timeout: .now() + 5) == .timedOut {
            throw NSError(domain: "cc.localserver", code: -1,
                          userInfo: [NSLocalizedDescriptionKey: "listener did not become ready"])
        }
        if let startError { throw startError }
        return port
    }

    func stop() {
        listener?.cancel()
        listener = nil
    }

    // MARK: - request handling

    /// HTTP headers can arrive split across TCP segments, so keep reading until the blank
    /// line that ends them. We never read a body: this server answers GET and HEAD only.
    private func receive(on conn: NWConnection, buffer: Data) {
        conn.receive(minimumIncompleteLength: 1, maximumLength: 16 * 1024) { [weak self] data, _, done, error in
            guard let self else { return }
            var buf = buffer
            if let data { buf.append(data) }

            if let range = buf.range(of: Data("\r\n\r\n".utf8)) {
                let head = String(decoding: buf[..<range.lowerBound], as: UTF8.self)
                self.respond(to: head, on: conn)
                return
            }
            if error != nil || done || buf.count > 64 * 1024 {
                conn.cancel()
                return
            }
            self.receive(on: conn, buffer: buf)
        }
    }

    private func respond(to head: String, on conn: NWConnection) {
        let line = head.split(separator: "\r\n", maxSplits: 1).first.map(String.init) ?? ""
        let parts = line.split(separator: " ")
        guard parts.count >= 2, parts[0] == "GET" || parts[0] == "HEAD" else {
            return send(status: "405 Method Not Allowed", body: Data(), type: "text/plain", on: conn)
        }
        let headOnly = parts[0] == "HEAD"

        var path = String(parts[1])
        if let q = path.firstIndex(of: "?") { path = String(path[..<q]) }
        path = path.removingPercentEncoding ?? path
        if path.hasSuffix("/") { path += "index.html" }
        if path == "" { path = "/index.html" }

        guard let file = resolve(path, in: overlay) ?? resolve(path, in: root) else {
            return send(status: "404 Not Found", body: Data("not found".utf8), type: "text/plain", on: conn)
        }
        guard let body = try? Data(contentsOf: file) else {
            return send(status: "500 Internal Server Error", body: Data(), type: "text/plain", on: conn)
        }
        send(status: "200 OK", body: headOnly ? Data() : body,
             type: Self.mime(for: file.pathExtension), length: body.count, on: conn)
    }

    /// Resolves inside `root` only. `standardized` collapses any `..` BEFORE the prefix test,
    /// so a crafted path cannot climb out of the bundle and serve arbitrary app files.
    private func resolve(_ path: String, in dir: URL?) -> URL? {
        guard let dir else { return nil }
        let url = dir.appendingPathComponent(path).standardizedFileURL
        let base = dir.standardizedFileURL.path
        guard url.path == base || url.path.hasPrefix(base + "/") else { return nil }
        var isDir: ObjCBool = false
        guard FileManager.default.fileExists(atPath: url.path, isDirectory: &isDir), !isDir.boolValue else { return nil }
        return url
    }

    private func send(status: String, body: Data, type: String, length: Int? = nil, on conn: NWConnection) {
        var header = "HTTP/1.1 \(status)\r\n"
        header += "Content-Type: \(type)\r\n"
        header += "Content-Length: \(length ?? body.count)\r\n"
        header += "Cache-Control: no-store\r\n"     // the bundle IS the cache
        header += "Connection: close\r\n\r\n"
        conn.send(content: Data(header.utf8) + body, completion: .contentProcessed { _ in
            conn.cancel()
        })
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
