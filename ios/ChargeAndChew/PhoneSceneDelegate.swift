import UIKit

/// The phone window. Scenes came back for CarPlay's sake -- a CarPlay app must be scene
/// based -- but the delegate is assigned by TYPE in AppDelegate.configurationForConnecting,
/// never by the string lookup in Info.plist that silently failed before.
final class PhoneSceneDelegate: UIResponder, UIWindowSceneDelegate {
    var window: UIWindow?
    private var web: WebViewController?

    func scene(_ scene: UIScene, willConnectTo session: UISceneSession, options: UIScene.ConnectionOptions) {
        guard let ws = scene as? UIWindowScene else { return }
        let vc = WebViewController()
        let w = UIWindow(windowScene: ws)
        w.rootViewController = vc
        w.makeKeyAndVisible()
        window = w; web = vc
        if let url = options.urlContexts.first?.url { vc.open(deepLink: url) }
    }

    /// ccapp://stop?at=LAT,LON — a tap on the widget lands on that stop.
    func scene(_ scene: UIScene, openURLContexts contexts: Set<UIOpenURLContext>) {
        if let url = contexts.first?.url { web?.open(deepLink: url) }
    }
}
