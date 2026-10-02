# gPodder 3.8.5 für Harmattan mit TLS 1.2/1.3

Zweig `harmattan-tls`, aufgesetzt auf dem Upstream-Tag `harmattan/gpodder_3.8.5`
(thp's Harmattan-Packaging; nach 3.8.5 wurde die QML-Oberfläche entfernt, Commit
28075c09). Dazu die drei brauchbaren Fixes zwischen 3.8.5 und dem Ende der
QML-UI als Cherry-Picks.

## Was fehlt dem Original

1. **TLS.** Pythons `_ssl` auf Harmattan spricht nur TLS 1.0 ohne SNI.
   `src/gpodder/tlsfix.py` fährt per ctypes die OpenSSL 1.1.1w aus
   `/opt/wunderw/lib` (N950 und N9) und ersetzt `httplib.HTTPSConnection.connect`;
   damit laufen urllib2, urllib.FancyURLopener (Downloads), feedparser und
   mygpoclient darüber. Zertifikate gegen `share/gpodder/ca-bundle.crt`
   (`GPODDER_TLS_NOVERIFY=1` schaltet ab). Fehlt die Bibliothek, passiert nichts.
2. **Qt-OpenSSL-Pin.** `python2.6` ist gegen OpenSSL 0.9.8 gelinkt (global).
   Qt 4.7.4 lädt später faul `libssl.so.1.0.0` und findet seit 1.0.2u in
   `/usr/local/lib` genau diese; deren Symbole binden an die 0.9.8 → SIGSEGV
   ~20 s nach dem Start, sobald Qt SSL anfasst. `tlsfix.pin_qt_openssl()` lädt
   das 1.0.2-Paar vorab mit RTLD_DEEPBIND (`GPODDER_NO_QT_SSL_PIN=1` schaltet ab).
   Diagnose: `strace -f -tt -e trace=file,process,network,signal`.

3. **Streamen.** Harmattans gstreamer-0.10 `souphttpsrc` ist ohne SSL gebaut
   und antwortet auf jede https-Adresse mit `SSL support not available` --
   Herunterladen ging deshalb immer, Streamen nie. Das Shim hilft dort nicht,
   es sitzt nur in Pythons httplib. `src/gpodder/streamproxy.py` stellt einen
   kleinen HTTP-Dienst auf 127.0.0.1, holt die Folge per urllib2 (also mit
   TLS 1.3) und reicht sie unverschlüsselt über die Rückschleife weiter;
   Range-Anfragen gehen in beide Richtungen durch, damit das Springen
   erhalten bleibt. `GPODDER_NO_STREAM_PROXY=1` schaltet ab.
   Der billige Weg von `smatkovi/sr` (https stumpf auf http umschreiben)
   reicht nicht: ORF leitet http auf https um. Aus demselben Grund laufen
   **auch reine http-Adressen** über den Vermittler -- sonst landet die
   Umleitung einen Schritt später wieder beim Player.

## Bauen und einspielen

    tools/harmattan-tls/build-deb.sh                       # arch + docker ubuntu:20.04
    # Gerät:  sudo apt-get install python-feedparser python-conic   (deps.sh)
    #         sudo aegis-dpkg -i gpodder_3.8.5+tls4_all.deb

`debian/compat` steht auf 7 und `dh_builddeb -- -Zgzip`, damit das Paket von
Harmattans altem dpkg gelesen wird. `tlstest.py` prüft das Shim am Gerät
(badssl-Negativtests, TLS-Version).

Gemessen am N950 (2026-10-02): TLSv1.3 / TLS_AES_256_GCM_SHA384, Abo + Cover
über HTTPS, Oberfläche per Sitzungsbus-Start > 90 s stabil, Streamen über den
Vermittler (206 auf Bereichsanfragen, gstreamer spielt).

Veröffentlicht als `harmattan-3.8.5+tls4` in `smatkovi/gpodder`.
