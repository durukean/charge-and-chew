import UIKit
import WebKit

/// Hosts the app. The web layer is the UI; everything native lives behind it -- the loopback
/// server, CoreLocation, and the data refresh.
final class WebViewController: UIViewController {

    private var server: LocalServer?
    private var bridge: NativeBridge?
    private var webView: WKWebView!
    private let splash = UIView()

    private var webRoot: URL? {
        Bundle.main.url(forResource: "Web", withExtension: nil)
    }

    override func viewDidLoad() {
        super.viewDidLoad()
        Diag.reset()
        Diag.log("viewDidLoad; webRoot=\(webRoot?.path ?? "NIL")")
        view.backgroundColor = UIColor { $0.userInterfaceStyle == .dark
            ? UIColor(red: 0.04, green: 0.05, blue: 0.07, alpha: 1)
            : UIColor(red: 0.96, green: 0.96, blue: 0.97, alpha: 1) }

        buildWebView()
        buildSplash()
        startServing()
    }

    // MARK: - web view

    private func buildWebView() {
        let cfg = WKWebViewConfiguration()
        cfg.allowsInlineMediaPlayback = true
        cfg.mediaTypesRequiringUserActionForPlayback = []

        let controller = WKUserContentController()
        controller.addUserScript(WKUserScript(source: NativeBridge.shimJS,
                                              injectionTime: .atDocumentStart,
                                              forMainFrameOnly: true))
        cfg.userContentController = controller

        webView = WKWebView(frame: .zero, configuration: cfg)
        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.allowsLinkPreview = false
        webView.isOpaque = false
        webView.backgroundColor = .clear
        // The map handles its own pinch/zoom; a rubber-banding page underneath it makes the
        // whole app feel like a website in a box, which is exactly the wrong impression.
        webView.scrollView.bounces = false
        webView.scrollView.contentInsetAdjustmentBehavior = .never

        bridge = NativeBridge(webView: webView)
        controller.add(bridge!, name: NativeBridge.name)

        webView.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(webView)
        NSLayoutConstraint.activate([
            webView.topAnchor.constraint(equalTo: view.topAnchor),
            webView.bottomAnchor.constraint(equalTo: view.bottomAnchor),
            webView.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            webView.trailingAnchor.constraint(equalTo: view.trailingAnchor),
        ])
    }

    /// Covers the white flash between launch-screen teardown and first paint. Removed on
    /// first successful navigation, never on a timer -- a timer that fires early shows a
    /// blank page and looks broken.
    private func buildSplash() {
        splash.backgroundColor = view.backgroundColor
        splash.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(splash)
        NSLayoutConstraint.activate([
            splash.topAnchor.constraint(equalTo: view.topAnchor),
            splash.bottomAnchor.constraint(equalTo: view.bottomAnchor),
            splash.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            splash.trailingAnchor.constraint(equalTo: view.trailingAnchor),
        ])

        let mark = UIImageView(image: UIImage(named: "LaunchMark"))
        mark.contentMode = .scaleAspectFit
        mark.translatesAutoresizingMaskIntoConstraints = false
        splash.addSubview(mark)
        NSLayoutConstraint.activate([
            mark.centerXAnchor.constraint(equalTo: splash.centerXAnchor),
            mark.centerYAnchor.constraint(equalTo: splash.centerYAnchor),
            mark.widthAnchor.constraint(equalToConstant: 96),
            mark.heightAnchor.constraint(equalToConstant: 96),
        ])
    }

    private func hideSplash() {
        guard splash.superview != nil else { return }
        UIView.animate(withDuration: 0.25, animations: { self.splash.alpha = 0 }) { _ in
            self.splash.removeFromSuperview()
        }
    }

    // MARK: - serving

    private func startServing() {
        guard let root = webRoot else { return showFailure("The app bundle is missing its web assets.") }

        let server = LocalServer(root: root)
        server.overlay = DataUpdater.overlayDir
        self.server = server

        do {
            let port = try server.start()
            let url = URL(string: "http://127.0.0.1:\(port)/index.html?src=ios")!
            Diag.log("serving \(url.absoluteString) from \(root.path)")
            webView.load(URLRequest(url: url))
        } catch {
            Diag.log("server start FAILED: \(error)")
            return showFailure("Could not start the local server.")
        }

        // Fire and forget. The app is already usable from the bundled copy; a newer dataset
        // simply lands on the next launch rather than yanking the map out from under anyone
        // mid-session.
        DataUpdater.refresh(bundled: root.appendingPathComponent("data.js")) { _ in }
    }

    private func showFailure(_ message: String) {
        let label = UILabel()
        label.text = message
        label.numberOfLines = 0
        label.textAlignment = .center
        label.font = .systemFont(ofSize: 15, weight: .medium)
        label.textColor = .secondaryLabel
        label.translatesAutoresizingMaskIntoConstraints = false
        splash.addSubview(label)
        NSLayoutConstraint.activate([
            label.centerXAnchor.constraint(equalTo: splash.centerXAnchor),
            label.centerYAnchor.constraint(equalTo: splash.centerYAnchor, constant: 80),
            label.widthAnchor.constraint(equalTo: splash.widthAnchor, multiplier: 0.75),
        ])
    }

    override var preferredStatusBarStyle: UIStatusBarStyle { .default }
}

extension WebViewController: WKNavigationDelegate {

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        Diag.log("didFinish \(webView.url?.absoluteString ?? "?")")
        hideSplash()
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        Diag.log("didFailProvisional: \(error)")
        showFailure("Could not reach the app's local server.")
    }

    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        Diag.log("web content process terminated")
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        Diag.log("didFail: \(error)")
        showFailure("Something went wrong loading the app.")
    }

    /// Anything that is not our own loopback origin is somebody else's website -- Google
    /// Maps directions, the AFDC source, a GitHub issue. Those belong in Safari, not inside
    /// the app with no way back.
    func webView(_ webView: WKWebView,
                 decidePolicyFor action: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = action.request.url else { return decisionHandler(.cancel) }
        if url.host == "127.0.0.1" || url.scheme == "about" {
            return decisionHandler(.allow)
        }
        if let scheme = url.scheme, ["http", "https", "mailto", "tel", "maps"].contains(scheme) {
            UIApplication.shared.open(url)
        }
        decisionHandler(.cancel)
    }
}

extension WebViewController: WKUIDelegate {
    /// target="_blank" arrives here rather than through the navigation policy, and every
    /// such link in the app is an outbound one.
    func webView(_ webView: WKWebView, createWebViewWith cfg: WKWebViewConfiguration,
                 for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = action.request.url, url.host != "127.0.0.1" {
            UIApplication.shared.open(url)
        }
        return nil
    }
}
