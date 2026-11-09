# Third-party notices

This local Windows package contains or uses the components below. Review their current license terms and provide any source, notices, relinking, and replacement rights those terms require before public ZIP distribution.

| Component | Version | License and notice |
| --- | --- | --- |
| Python | 3.13.3 build environment | PSF License: https://docs.python.org/3/license.html |
| PySide6 and Qt runtime | 6.9.2 | Qt for Python Community Edition is available under LGPLv3/GPLv3; commercial terms are also available. The wheel's supplied Qt commercial license reference is in `licenses/`. See https://doc.qt.io/qtforpython-6/licenses.html and https://doc.qt.io/qt-6/licensing.html. |
| Shiboken6 | 6.9.2 | Qt for Python licensing; supplied wheel license reference is in `licenses/`. See https://doc.qt.io/qtforpython-6/licenses.html. |
| PyInstaller | 6.22.3 | GPLv2-or-later with the Bootloader Exception. The complete notice is in `licenses/COPYING.txt`. See https://github.com/pyinstaller/pyinstaller/blob/develop/COPYING.txt. |
| aria2 | External prerequisite, not included | GPL-2.0. Obtain and install it separately; see https://github.com/aria2/aria2. |
| Dashboard browser assets | Next.js 16, React 19, Lucide React 1.70, Tailwind CSS 4 | The bundled static export includes third-party JavaScript and CSS. Package-specific notices and license files must be collected from the npm dependency tree before public redistribution. |

The package builder copies license files supplied with the pinned PySide6, Shiboken6, and PyInstaller wheels. Qt's community licensing options and the obligations for this PyInstaller one-folder bundle still require release review; this notice is not a legal determination.
