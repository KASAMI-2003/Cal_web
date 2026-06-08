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
- `POST /api/vasp/import` -> `{ success, auto_rejected?, id?, message, stability?, db_data?, quality?, calc_meta? }`（Born/Mouhat 通过后进入待审核）

  可选质量字段（JSON 体，均可省略）：

  | 字段 | 说明 |
  |------|------|
  | `strain_fit_residual` | 应变拟合残差 |
  | `k_convergence_tier` | k 点收敛档位 |
  | `calc_exp_deviation_label` | 计算—实验偏差标签 |

  中文别名：`应变拟合残差`、`k点收敛档位`、`计算—实验偏差标签` 亦可。
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

- ~~`POST /mysql_changeData`~~ — implemented in `cal_platform/legacy_handlers.py`
- ~~`POST /create_matrix`~~ — implemented
- ~~`POST /execute_ssh`~~ — implemented

## New endpoints (2026-06 thesis alignment)

- `POST /api/home_search` — parallel local + MP home search
- `POST /api/data_fit/link_compound` — link fit result to compound (JWT optional)
- `GET /api/outcar_tail?dir=` — OUTCAR tail preview
- `GET /api/extended_properties?work_dir=&module=` — 能带/DOS/声子文件探测与摘要（`module`: all | band_structure | dos | phonon）
- `POST /api/extended_properties/scan` — body `{ work_dir, module? }`
- `POST /api/convergence/scan` — ENCUT/k 收敛扫描，body `{ root_dir, threshold_gpa? }`（默认 2 GPa）
- `GET /api/digital_twin/metal_presets` — thesis metal Cij presets
- `GET /api/digital_twin/fedorov_crosscheck?symbol=` — offline cross-check
- Rust: `GET /auth/verify` — JWT validation; login returns `{ data: { token, username } }`

`POST /page2_search` body may include `filters`: `{ structure, method, stability, young_min, young_max }`.
