import Foundation
import CoreLocation
import WebKit

/// Native location, handed to the web layer.
///
/// WKWebView does not give a web page CoreLocation on its own -- `navigator.geolocation`
/// inside a WKWebView has never been reliable without private API -- so the page's
/// geolocation is replaced at document start with a shim that asks Swift instead. That also
/// buys the honest thing: the system permission sheet, with our own usage string, at the
/// moment the user taps the locate button rather than on launch.
final class NativeBridge: NSObject {

    static let name = "cc"

    /// Replaces navigator.geolocation before any app code runs. The web app already handles
    /// PositionError shapes, so the shim mimics the real API exactly rather than inventing
    /// a second contract the page would have to learn.
    static let shimJS = """
    (function () {
      var pending = {}, nextId = 1;
      function call(cmd, opts, ok, err) {
        var id = nextId++;
        pending[id] = { ok: ok, err: err };
        window.webkit.messageHandlers.cc.postMessage({ cmd: cmd, id: id, opts: opts || {} });
        return id;
      }
      window.__ccNative = {
        version: 1,
        resolve: function (id, coords) {
          var p = pending[id]; if (!p) return;
          if (!p.watch) delete pending[id];
          p.ok && p.ok({ coords: coords, timestamp: Date.now() });
        },
        reject: function (id, code, message) {
          var p = pending[id]; if (!p) return;
          delete pending[id];
          p.err && p.err({ code: code, message: message,
                           PERMISSION_DENIED: 1, POSITION_UNAVAILABLE: 2, TIMEOUT: 3 });
        }
      };
      navigator.geolocation.getCurrentPosition = function (ok, err, opts) {
        call('locate', opts, ok, err);
      };
      navigator.geolocation.watchPosition = function (ok, err, opts) {
        var id = call('watch', opts, ok, err);
        pending[id].watch = true;
        return id;
      };
      navigator.geolocation.clearWatch = function (id) {
        delete pending[id];
        window.webkit.messageHandlers.cc.postMessage({ cmd: 'clearWatch', id: id });
      };
    })();
    """

    private let manager = CLLocationManager()
    private weak var webView: WKWebView?
    /// Requests parked until the user answers the permission sheet.
    private var waiting: [(id: Int, watch: Bool)] = []
    private var watching = Set<Int>()

    init(webView: WKWebView) {
        self.webView = webView
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyHundredMeters
    }

    private func reply(_ id: Int, _ loc: CLLocation) {
        let c = loc.coordinate
        let js = """
        window.__ccNative.resolve(\(id), {latitude: \(c.latitude), longitude: \(c.longitude), \
        accuracy: \(max(loc.horizontalAccuracy, 1)), altitude: null, altitudeAccuracy: null, \
        heading: null, speed: null});
        """
        DispatchQueue.main.async { self.webView?.evaluateJavaScript(js) }
    }

    private func fail(_ id: Int, _ code: Int, _ message: String) {
        let safe = message.replacingOccurrences(of: "'", with: "")
        DispatchQueue.main.async {
            self.webView?.evaluateJavaScript("window.__ccNative.reject(\(id), \(code), '\(safe)')")
        }
    }

    private func serve(id: Int, watch: Bool) {
        switch manager.authorizationStatus {
        case .notDetermined:
            waiting.append((id, watch))
            manager.requestWhenInUseAuthorization()
        case .denied, .restricted:
            fail(id, 1, "Location permission denied")
        default:
            begin(id: id, watch: watch)
        }
    }

    private func begin(id: Int, watch: Bool) {
        if watch {
            watching.insert(id)
            manager.startUpdatingLocation()
        } else {
            waiting.append((id, false))
            manager.requestLocation()
        }
    }
}

extension NativeBridge: WKScriptMessageHandler {
    func userContentController(_ c: WKUserContentController, didReceive message: WKScriptMessage) {
        guard let body = message.body as? [String: Any],
              let cmd = body["cmd"] as? String,
              let id = body["id"] as? Int else { return }
        switch cmd {
        case "locate": serve(id: id, watch: false)
        case "watch":  serve(id: id, watch: true)
        case "clearWatch":
            watching.remove(id)
            if watching.isEmpty { manager.stopUpdatingLocation() }
        default: break
        }
    }
}

extension NativeBridge: CLLocationManagerDelegate {
    func locationManagerDidChangeAuthorization(_ m: CLLocationManager) {
        switch m.authorizationStatus {
        case .notDetermined:
            break                                  // sheet still up
        case .denied, .restricted:
            let parked = waiting; waiting = []
            parked.forEach { fail($0.id, 1, "Location permission denied") }
        default:
            let parked = waiting; waiting = []
            parked.forEach { begin(id: $0.id, watch: $0.watch) }
        }
    }

    func locationManager(_ m: CLLocationManager, didUpdateLocations locs: [CLLocation]) {
        guard let loc = locs.last else { return }
        let parked = waiting; waiting = []
        parked.forEach { reply($0.id, loc) }
        watching.forEach { reply($0, loc) }
    }

    func locationManager(_ m: CLLocationManager, didFailWithError error: Error) {
        let parked = waiting; waiting = []
        parked.forEach { fail($0.id, 2, "Could not get a location fix") }
    }
}
