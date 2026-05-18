# API Contract Freeze

This file freezes backend contracts used by the TSX migration.

## Python (`pyserver.py`, same-origin)

- `GET /api/data` -> `{ "message": string[] }`
- `POST /api/submit` -> `{ status, message }`
- `POST /mysql_receive` -> `{ message, db_meta?, db_materials? }`
- `POST /page2_search` -> `{ elements, materials, error? }`
- `GET /data_input/my?username=...` -> `{ success, data }`
- `GET /data_input/pending?admin_user=admin` -> `{ success, data }`
- `PUT /data_input/review` -> `{ success, message }`
- `POST /data_input/submit` -> `{ success, message, id? }`
- `POST /api/data_fit` -> `{ status, fit_func, r_squared, coeffs, x_fit, y_fit }` or `{ status: "error", message }`
- `POST /api/terminal_reachable` -> `{ ok, reachable, ...detail }`
- `GET /websocket_port` -> `{ port }`
- `GET /api/digital_twin/properties`
- `GET /api/digital_twin/anisotropy_surface`
- `GET /api/digital_twin/capabilities`
- `GET /api/digital_twin/list_dat`
- `POST /api/digital_twin/upload_dat`
- `POST /api/digital_twin/activate_dat`

## Rust (`http://127.0.0.1:8088`)

- `POST /register`
- `POST /login`
- `GET /users/info?username=...`
- `PUT /users/update`
- `GET /health`

## Known gaps (frontend calls but no handler in `pyserver.py`)

- `POST /mysql_changeData`
- `POST /create_matrix`
- `POST /execute_ssh`

TSX migration handles these as optional/legacy to avoid blocking rollout.
