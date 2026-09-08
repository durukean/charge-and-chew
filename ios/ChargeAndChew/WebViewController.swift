import UIKit
import WebKit
import SafariServices

/// Hosts the app. The web layer is the UI; everything native lives behind it -- the loopback
/// server, CoreLocation, the share sheet, haptics, and the data refresh.
final class WebViewController: UIViewController {

    private var bridge: NativeBridge?
    private var webView: WKWebView!
    private let splash = UIView()
    private var dark = false

    private static let siteHost = "chargeandchew.com"
    private var webRoot: URL? { Bundle.main.url(forResource: "Web", withExtension: nil) }

    private static let lightBG = UIColor(red: 0.96, green: 0.96, blue: 0.97, alpha: 1)
    private static let darkBG  = UIColor(red: 0.04, green: 0.05, blue: 0.07, alpha: 1)

    override func viewDidLoad() {
        super.viewDidLoad()
        Diag.reset()
        Diag.log("viewDidLoad; webRoot=\(webRoot?.path ?? "NIL")")
        // Until the page reports its own theme, follow the system so the splash does not
        // flash the wrong colour on the way in.
        dark = traitCollection.userInterfaceStyle == .dark
        view.backgroundColor = dark ? Self.darkBG : Self.lightBG
        buildWebView()
        buildSplash()
        startServing()
    }

    // MARK: - web view

    private func buildWebView() {
        let cfg = WKWebViewConfiguration()
        if let root = webRoot {
            let handler = AppSchemeHandler(root: root)
            handler.overlay = DataUpdater.overlayDir
            cfg.setURLSchemeHandler(handler, forURLScheme: AppSchemeHandler.scheme)
        }
        cfg.allowsInlineMediaPlayback = true
        cfg.mediaTypesRequiringUserActionForPlayback = []

        let controller = WKUserContentController()
        controller.addUserScript(WKUserScript(source: NativeBridge.shimJS,
                                              injectionTime: .atDocumentStart,
                                              forMainFrameOnly: true))
        cfg.userContentController = controller

        webView = AppWebView(frame: .zero, configuration: cfg)
        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.allowsLinkPreview = false
        webView.isOpaque = false
        webView.backgroundColor = .clear
        // The map handles its own pinch/zoom; a rubber-banding page underneath it makes the
        // whole app feel like a website in a box, which is exactly the wrong impression.
        webView.scrollView.bounces = false
        webView.scrollView.contentInsetAdjustmentBehavior = .never

        let bridge = NativeBridge(webView: webView)
        bridge.onShare = { [weak self] url, title in self?.share(url, title: title) }
        bridge.onTheme = { [weak self] isDark in self?.applyTheme(dark: isDark) }
        bridge.onLocationDenied = { [weak self] in self?.offerLocationSettings() }
        controller.add(bridge, name: NativeBridge.name)
        self.bridge = bridge

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
        let url = URL(string: "\(AppSchemeHandler.origin)/index.html?src=ios")!
        Diag.log("loading \(url.absoluteString)")
        webView.load(URLRequest(url: url))
        // Fire and forget. The app is already usable from the bundled copy; a newer dataset
        // simply lands on the next launch rather than yanking the map out from under anyone.
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

    // MARK: - native services for the page

    /// The page runs its own solar theme -- light by day, dark by night -- independent of the
    /// system setting, so the status bar has to follow the page, not the system. Without
    /// this the clock is black-on-black every evening for anyone with light mode on.
    private func applyTheme(dark: Bool) {
        self.dark = dark
        view.backgroundColor = dark ? Self.darkBG : Self.lightBG
        setNeedsStatusBarAppearanceUpdate()
    }
    override var preferredStatusBarStyle: UIStatusBarStyle { dark ? .lightContent : .darkContent }

    /// Once location is denied, every later tap on the locate button would fail silently --
    /// the page's toast is gone in three seconds and iOS will never show the permission
    /// sheet again. The only way back is Settings, so offer the shortcut.
    private func offerLocationSettings() {
        guard presentedViewController == nil else { return }
        let alert = UIAlertController(
            title: "Location is off for Charge & Chew",
            message: "Turn it on in Settings to find chargers near you. You can also just search a city or drop a pin.",
            preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "Not now", style: .cancel))
        alert.addAction(UIAlertAction(title: "Open Settings", style: .default) { _ in
            if let url = URL(string: UIApplication.openSettingsURLString) { UIApplication.shared.open(url) }
        })
        present(alert, animated: true)
    }

    private func share(_ url: URL, title: String) {
        let sheet = UIActivityViewController(activityItems: [url], applicationActivities: nil)
        present(sheet, animated: true)
    }

    /// Where an outside URL goes. Google Maps links are handed to the system so the Google
    /// Maps app can claim them (Universal Links do not fire inside SFSafariViewController);
    /// everything else opens in an in-app Safari sheet with a Done button, which keeps the
    /// user in the app instead of bouncing them out to Safari with no way back.
    private func openExternal(_ url: URL) {
        guard let scheme = url.scheme?.lowercased() else { return }
        if scheme != "http" && scheme != "https" {
            UIApplication.shared.open(url); return
        }
        let host = url.host?.lowercased() ?? ""
        if host.hasSuffix("google.com") && url.path.hasPrefix("/maps") {
            // Directions: if the Google Maps app is installed the Universal Link takes it;
            // otherwise Google serves a mobile web page whose main feature is a nag to
            // install the app. Apple Maps is on every iPhone and gives real turn-by-turn,
            // so that is the fallback -- not Safari.
            if url.path.hasPrefix("/maps/dir"), !UIApplication.shared.canOpenURL(URL(string: "comgooglemaps://")!),
               let apple = appleMapsDirections(from: url) {
                UIApplication.shared.open(apple); return
            }
            UIApplication.shared.open(url); return
        }
        let safari = SFSafariViewController(url: url)
        safari.preferredControlTintColor = UIColor(red: 0.13, green: 0.77, blue: 0.37, alpha: 1)
        present(safari, animated: true)
    }

    /// google.com/maps/dir/?api=1&destination=LAT,LON&travelmode=walking -> maps://
    private func appleMapsDirections(from url: URL) -> URL? {
        guard let items = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems,
              let dest = items.first(where: { $0.name == "destination" })?.value else { return nil }
        let walking = items.first(where: { $0.name == "travelmode" })?.value == "walking"
        var c = URLComponents(string: "maps://")!
        c.queryItems = [URLQueryItem(name: "daddr", value: dest),
                        URLQueryItem(name: "dirflg", value: walking ? "w" : "d")]
        return c.url
    }

    /// The SEO pages (/near/…, /along/…, /trip/…) are not in the bundle -- they are for
    /// Google, not the app -- so a tap on one must land on the real site, not a 404 from the
    /// loopback server.
    private func siteURL(forLocalPath path: String, query: String?) -> URL {
        var c = URLComponents()
        c.scheme = "https"; c.host = Self.siteHost
        c.path = path.hasSuffix("/index.html") ? String(path.dropLast("index.html".count)) : path
        c.query = query
        return c.url!
    }
}

extension WebViewController: WKNavigationDelegate {

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        Diag.log("didFinish \(webView.url?.absoluteString ?? "?")")
        hideSplash()
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        Diag.log("didFail: \(error)")
        showFailure("Something went wrong loading the app.")
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        Diag.log("didFailProvisional: \(error)")
        showFailure("Could not load the app.")
    }

    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        // iOS reclaims the content process under memory pressure; a blank white view is what
        // the user sees unless we reload.
        Diag.log("web content process terminated; reloading")
        webView.reload()
    }

    func webView(_ webView: WKWebView,
                 decidePolicyFor action: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = action.request.url else { return decisionHandler(.cancel) }
        if url.scheme == "about" { return decisionHandler(.allow) }
        if url.scheme == AppSchemeHandler.scheme {
            // The app itself is one page. Any other main-frame path is a site page.
            if action.targetFrame?.isMainFrame == true, url.path != "/index.html", url.path != "/" {
                openExternal(siteURL(forLocalPath: url.path, query: url.query))
                return decisionHandler(.cancel)
            }
            return decisionHandler(.allow)
        }
        openExternal(url)
        decisionHandler(.cancel)
    }
}

extension WebViewController: WKUIDelegate {
    /// target="_blank" arrives here rather than through the navigation policy, and every
    /// such link in the app is an outbound one.
    func webView(_ webView: WKWebView, createWebViewWith cfg: WKWebViewConfiguration,
                 for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = action.request.url {
            if url.scheme == AppSchemeHandler.scheme { openExternal(siteURL(forLocalPath: url.path, query: url.query)) }
            else { openExternal(url) }
        }
        return nil
    }
}
