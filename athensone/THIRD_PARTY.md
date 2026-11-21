# Third-Party Dependencies and Licences

AthensOne is released under the MIT licence. All third-party packages and assets used by the application are listed below with their licences.

## Python backend (`requirements.txt`)

| Package | Version / Pin | Licence | Role | Source |
|---|---|---|---|---|
| `fastapi` | `>=0.110` | MIT | HTTP API framework | https://github.com/fastapi/fastapi |
| `uvicorn` | `>=0.29` | BSD-3-Clause | ASGI server | https://github.com/Kludex/uvicorn |
| `httpx` | `>=0.27` | BSD-3-Clause | HTTP client (sandbox, Valhalla, CKAN, Open-Meteo, vision) | https://github.com/encode/httpx |
| `python-multipart` | `>=0.0.9` | Apache-2.0 | Multipart form/photo upload parsing | https://github.com/Kludex/python-multipart |
| `pillow` | `>=10` | MIT-CMU (HPND) | Image decoding, EXIF GPS extraction, orientation transpose | https://github.com/python-pillow/Pillow |
| `opencv-python-headless` | `>=4.9,<5` | Apache-2.0 | Image encoding, Gaussian blur, `cv2.dnn` inference, Haar cascade fallback | https://github.com/opencv/opencv-python |
| `numpy` | `>=1.26` | BSD-3-Clause | Array operations for photo processing and face detection | https://github.com/numpy/numpy |
| `python-dotenv` | `>=1.0` | BSD-3-Clause | `.env` configuration loading | https://github.com/theskumar/python-dotenv |
| `pytest` | `>=8` | MIT | Offline test suite | https://github.com/pytest-dev/pytest |
| `scikit-image` | `>=0.22` | BSD-3-Clause | Bundled offline face test fixture (`skimage.data.astronaut`) in `tests/test_T5_blur.py` | https://github.com/scikit-image/scikit-image |

### T5: Face detection (`deface` / CenterFace)

| Package | Version / Pin | Licence | Role | Source |
|---|---|---|---|---|
| `deface` (bundles `centerface.onnx`) | `==1.5.0` (installed with `pip install --no-deps deface==1.5.0`) | MIT (`Copyright (c) 2020 Martin Drawitsch`, verified in installed `deface-1.5.0` metadata) | Primary face detector (`deface.centerface.CenterFace`) in `app/privacy.py`, with automatic fallback to OpenCV Haar cascades. Runs on OpenCV `cv2.dnn` without `onnxruntime`. | https://github.com/ORB-HD/deface |

> **Install note (OpenCV 4.x compatibility):** `deface==1.5.0` declares `opencv-python` (unpinned, resolving to 5.x, which removes `cv2.CascadeClassifier`). Always install `deface` with `pip install --no-deps deface==1.5.0` after `requirements.txt` so `opencv-python-headless>=4.9,<5` remains intact. `deface.centerface.CenterFace` only imports `os`, `functools`, `numpy`, and `cv2`.
>
> **Model weights:** `centerface.onnx` comes from CenterFace (https://github.com/Star-Clouds/CenterFace), MIT licence
> (from memory, not re-checked tonight: open its LICENSE before the final push). `onnxruntime` (MIT) is not installed;
> the model runs on OpenCV `cv2.dnn`.

## Frontend & accessibility (`web/`, `package.json`)

| Package / Asset | Version | Licence | Role | Source |
|---|---|---|---|---|
| `maplibre-gl` | `4.7.1` | BSD-3-Clause | Interactive map rendering (`web/citizen.html`, `web/operator.html`) | https://github.com/maplibre/maplibre-gl-js |
| OpenStreetMap tiles | — | ODbL 1.0 | Basemap tiles (`© OpenStreetMap` attribution shown) | https://www.openstreetmap.org/copyright |
| `axe-core` | `^4.10.0` | MPL-2.0 | Accessibility check dev dependency (`scripts/a11y_check.py`) | https://github.com/dequelabs/axe-core |
