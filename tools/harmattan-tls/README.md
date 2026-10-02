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

## Bauen und einspielen

    tools/harmattan-tls/build-deb.sh                       # arch + docker ubuntu:20.04
    # Gerät:  sudo apt-get install python-feedparser python-conic   (deps.sh)
    #         sudo aegis-dpkg -i gpodder_3.8.5+tls2_all.deb

`debian/compat` steht auf 7 und `dh_builddeb -- -Zgzip`, damit das Paket von
Harmattans altem dpkg gelesen wird. `tlstest.py` prüft das Shim am Gerät
(badssl-Negativtests, TLS-Version).

Gemessen am N950 (2026-10-02): TLSv1.3 / TLS_AES_256_GCM_SHA384, Abo + Cover
über HTTPS, Oberfläche per Sitzungsbus-Start > 90 s stabil.
