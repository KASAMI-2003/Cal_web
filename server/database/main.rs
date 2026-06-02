mod file_db;
use file_db::FileDatabase;
use std::collections::HashMap;
use std::env;
use actix_web::{web, App, HttpServer, HttpResponse, Responder};
use serde::{Deserialize, Serialize};
use std::sync::Mutex;
use actix_cors::Cors;
use bcrypt::{hash, verify, DEFAULT_COST};
use jsonwebtoken::{decode, encode, DecodingKey, EncodingKey, Header, Validation};
use chrono::{Duration, Utc};

const JWT_DEFAULT_SECRET: &str = "calweb-dev-jwt-secret-change-in-production";

#[derive(Serialize, Deserialize)]
struct Claims {
    sub: String,
    exp: usize,
}

fn jwt_secret() -> String {
    env::var("JWT_SECRET").unwrap_or_else(|_| JWT_DEFAULT_SECRET.to_string())
}

fn hash_password(password: &str) -> Result<String, bcrypt::BcryptError> {
    hash(password, DEFAULT_COST)
}

fn verify_password(stored: &str, input: &str) -> bool {
    if stored.starts_with("$2") {
        verify(input, stored).unwrap_or(false)
    } else {
        stored == input
    }
}

fn issue_jwt(username: &str) -> Result<String, jsonwebtoken::errors::Error> {
    let exp = (Utc::now() + Duration::days(7)).timestamp() as usize;
    let claims = Claims {
        sub: username.to_string(),
        exp,
    };
    encode(
        &Header::default(),
        &claims,
        &EncodingKey::from_secret(jwt_secret().as_bytes()),
    )
}

fn verify_jwt(token: &str) -> Option<String> {
    decode::<Claims>(
        token,
        &DecodingKey::from_secret(jwt_secret().as_bytes()),
        &Validation::default(),
    )
    .ok()
    .map(|d| d.claims.sub)
}

#[derive(Serialize)]
struct LoginData {
    token: String,
    username: String,
}

#[derive(Deserialize)]
struct RegisterInfo {
    username: String,
    password: String,
    #[serde(default)]
    email: Option<String>,
    #[serde(default)]
    phone: Option<String>,
}

#[derive(Deserialize)]
struct LoginInfo {
    username: String,
    password: String,
}

#[derive(Serialize)]
struct ApiResponse<T = ()> {
    success: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    message: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    data: Option<T>,
}

#[derive(Deserialize)]
struct CompoundQueryRequest {
    element: String,
    text: String, // 逗号分隔的列名，如 "晶体结构,晶格常数,弹性刚度常数C11,C12,杨氏模量E-H"
}

async fn health() -> impl Responder {
    HttpResponse::Ok().json(serde_json::json!({ "status": "ok" }))
}

async fn register(
    db: web::Data<Mutex<FileDatabase>>,
    info: web::Json<RegisterInfo>,
) -> impl Responder {
    let mut db = db.lock().unwrap();
    let mut columns = HashMap::new();
    columns.insert("username".to_string(), "string".to_string());
    columns.insert("password".to_string(), "string".to_string());
    db.create_table("users", columns);

    let mut user = HashMap::new();
    user.insert("username".to_string(), serde_json::Value::from(info.username.clone()));
    let password_hash = match hash_password(&info.password) {
        Ok(h) => h,
        Err(_) => {
            return HttpResponse::InternalServerError().json(ApiResponse::<()> {
                success: false,
                message: Some("密码哈希失败".to_string()),
                data: None,
            });
        }
    };
    user.insert("password_hash".to_string(), serde_json::Value::from(password_hash));
    user.insert("email".to_string(), serde_json::Value::from(info.email.clone().unwrap_or_default()));
    user.insert("phone".to_string(), serde_json::Value::from(info.phone.clone().unwrap_or_default()));
    user.insert("create_time".to_string(), serde_json::Value::from(chrono::Utc::now().timestamp()));
    let cond: HashMap<String, serde_json::Value> = [("username".to_string(), serde_json::Value::from(info.username.clone()))]
        .iter()
        .cloned()
        .collect();
    let exists = db.select("users", Some(cond)).len() > 0;
    if exists {
        return HttpResponse::BadRequest().json(ApiResponse::<()> {
            success: false,
            message: Some("User already exists".to_string()),
            data: None,
        });
    }
    db.insert("users", user);
    HttpResponse::Ok().json(ApiResponse::<()> {
        success: true,
        message: Some("Register success".to_string()),
        data: None,
    })
}

async fn login(
    db_data: web::Data<Mutex<FileDatabase>>,
    info: web::Json<LoginInfo>,
) -> impl Responder {
    let db = db_data.lock().unwrap();
    let mut cond = HashMap::new();
    cond.insert("username".to_string(), serde_json::Value::from(info.username.clone()));
    let found = db.select("users", Some(cond));
    if found.is_empty() {
        return HttpResponse::Unauthorized().json(ApiResponse::<()> {
            success: false,
            message: Some("Login failed".to_string()),
            data: None,
        });
    }
    let row = &found[0];
    let stored = row
        .get("password_hash")
        .or_else(|| row.get("password"))
        .and_then(|v| v.as_str())
        .unwrap_or("");
    if !verify_password(stored, &info.password) {
        return HttpResponse::Unauthorized().json(ApiResponse::<()> {
            success: false,
            message: Some("Login failed".to_string()),
            data: None,
        });
    }
    let username = info.username.clone();
    let needs_upgrade = !stored.starts_with("$2");
    drop(db);
    if needs_upgrade {
        if let Ok(h) = hash_password(&info.password) {
            let db = db_data.lock().unwrap();
            let mut conditions = HashMap::new();
            conditions.insert("username".to_string(), serde_json::Value::from(username.clone()));
            let mut new_data = HashMap::new();
            new_data.insert("password_hash".to_string(), serde_json::Value::from(h));
            db.update("users", conditions, new_data);
        }
    }
    match issue_jwt(&username) {
        Ok(token) => HttpResponse::Ok().json(ApiResponse {
            success: true,
            message: Some("Login success".to_string()),
            data: Some(LoginData {
                token,
                username: username.clone(),
            }),
        }),
        Err(_) => HttpResponse::InternalServerError().json(ApiResponse::<()> {
            success: false,
            message: Some("JWT 签发失败".to_string()),
            data: None,
        }),
    }
}

async fn auth_verify(req: actix_web::HttpRequest) -> impl Responder {
    let auth = req
        .headers()
        .get("Authorization")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("");
    let token = auth.strip_prefix("Bearer ").unwrap_or("").trim();
    if let Some(username) = verify_jwt(token) {
        HttpResponse::Ok().json(ApiResponse {
            success: true,
            message: None,
            data: Some(serde_json::json!({ "username": username, "valid": true })),
        })
    } else {
        HttpResponse::Unauthorized().json(ApiResponse::<()> {
            success: false,
            message: Some("Invalid token".to_string()),
            data: None,
        })
    }
}

/// GET /users/info?username=xxx 获取用户信息（不含密码）
async fn users_info(
    db: web::Data<Mutex<FileDatabase>>,
    query: web::Query<HashMap<String, String>>,
) -> impl Responder {
    let db = db.lock().unwrap();
    let username = match query.get("username") {
        Some(s) => s.clone(),
        None => {
            return HttpResponse::BadRequest().json(ApiResponse::<HashMap<String, serde_json::Value>> {
                success: false,
                message: Some("缺少 username 参数".to_string()),
                data: None,
            });
        }
    };
    let mut cond = HashMap::new();
    cond.insert("username".to_string(), serde_json::Value::from(username.clone()));
    let found = db.select("users", Some(cond));
    if let Some(row) = found.into_iter().next() {
        let mut info = HashMap::new();
        for (k, v) in row {
            if k != "password" && k != "password_hash" {
                info.insert(k, v);
            }
        }
        HttpResponse::Ok().json(ApiResponse {
            success: true,
            message: None,
            data: Some(info),
        })
    } else {
        HttpResponse::NotFound().json(ApiResponse::<HashMap<String, serde_json::Value>> {
            success: false,
            message: Some("用户不存在".to_string()),
            data: None,
        })
    }
}

/// PUT /users/update 更新用户信息（email, phone）
#[derive(Deserialize)]
struct UserUpdateInfo {
    username: String,
    #[serde(default)]
    email: Option<String>,
    #[serde(default)]
    phone: Option<String>,
}

async fn users_update(
    db: web::Data<Mutex<FileDatabase>>,
    info: web::Json<UserUpdateInfo>,
) -> impl Responder {
    let db = db.lock().unwrap();
    let mut conditions = HashMap::new();
    conditions.insert("username".to_string(), serde_json::Value::from(info.username.clone()));
    let mut new_data = HashMap::new();
    if info.email.is_some() {
        new_data.insert("email".to_string(), serde_json::Value::from(info.email.clone().unwrap_or_default()));
    }
    if info.phone.is_some() {
        new_data.insert("phone".to_string(), serde_json::Value::from(info.phone.clone().unwrap_or_default()));
    }
    if new_data.is_empty() {
        return HttpResponse::BadRequest().json(ApiResponse::<()> {
            success: false,
            message: Some("需提供 email 或 phone 进行更新".to_string()),
            data: None,
        });
    }
    let ok = db.update("users", conditions, new_data);
    HttpResponse::Ok().json(ApiResponse::<()> {
        success: ok,
        message: Some(if ok { "更新成功" } else { "未找到用户" }.to_string()),
        data: None,
    })
}

/// GET /compounds?元素=xxx 或 GET /compounds 获取全部
async fn compounds_list(
    db: web::Data<Mutex<FileDatabase>>,
    query: web::Query<HashMap<String, String>>,
) -> impl Responder {
    let db = db.lock().unwrap();
    let conditions: Option<HashMap<String, serde_json::Value>> = query
        .get("元素")
        .map(|v| {
            let mut m = HashMap::new();
            m.insert("元素".to_string(), serde_json::Value::from(v.clone()));
            m
        });
    let rows = db.select("compounds", conditions);
    HttpResponse::Ok().json(ApiResponse {
        success: true,
        message: None,
        data: Some(rows),
    })
}

/// POST /compounds/query —— 与 Python /mysql_receive 兼容：body { element, text }，返回 { message: [v1,v2,...] }
async fn compounds_query(
    db: web::Data<Mutex<FileDatabase>>,
    body: web::Json<CompoundQueryRequest>,
) -> impl Responder {
    let db = db.lock().unwrap();
    let mut cond = HashMap::new();
    cond.insert("元素".to_string(), serde_json::Value::from(body.element.clone()));
    let rows = db.select("compounds", Some(cond));
    let columns: Vec<String> = body.text.split(',').map(|s| s.trim().to_string()).collect();
    let message: Vec<serde_json::Value> = if let Some(row) = rows.into_iter().next() {
        columns
            .iter()
            .map(|col| row.get(col).cloned().unwrap_or(serde_json::Value::Null))
            .collect()
    } else {
        columns.iter().map(|_| serde_json::Value::Null).collect()
    };
    HttpResponse::Ok().json(serde_json::json!({ "message": message }))
}

/// POST /compounds —— 插入一条化合物记录，body 为键值对
async fn compounds_insert(
    db: web::Data<Mutex<FileDatabase>>,
    body: web::Json<HashMap<String, serde_json::Value>>,
) -> impl Responder {
    let db = db.lock().unwrap();
    let row: HashMap<String, serde_json::Value> = body.into_inner();
    if !db.schema.tables.contains_key("compounds") {
        return HttpResponse::InternalServerError().json(ApiResponse::<()> {
            success: false,
            message: Some("表 compounds 不存在".to_string()),
            data: None,
        });
    }
    let ok = db.insert("compounds", row);
    if ok {
        HttpResponse::Ok().json(ApiResponse::<()> {
            success: true,
            message: Some("插入成功".to_string()),
            data: None,
        })
    } else {
        HttpResponse::BadRequest().json(ApiResponse::<()> {
            success: false,
            message: Some("插入失败".to_string()),
            data: None,
        })
    }
}

/// PUT /compounds —— 按 元素 更新一条记录，body 需包含 元素 及要更新的字段
async fn compounds_update(
    db: web::Data<Mutex<FileDatabase>>,
    body: web::Json<HashMap<String, serde_json::Value>>,
) -> impl Responder {
    let db = db.lock().unwrap();
    let body = body.into_inner();
    let element = match body.get("元素") {
        Some(serde_json::Value::String(s)) => s.clone(),
        _ => {
            return HttpResponse::BadRequest().json(ApiResponse::<()> {
                success: false,
                message: Some("body 需包含 元素".to_string()),
                data: None,
            });
        }
    };
    let mut conditions = HashMap::new();
    conditions.insert("元素".to_string(), serde_json::Value::String(element.clone()));
    let mut new_data = body;
    new_data.remove("元素");
    let ok = db.update("compounds", conditions, new_data);
    HttpResponse::Ok().json(ApiResponse::<()> {
        success: ok,
        message: Some(if ok { "更新成功" } else { "未找到匹配记录" }.to_string()),
        data: None,
    })
}

/// DELETE /compounds?元素=xxx
async fn compounds_delete(
    db: web::Data<Mutex<FileDatabase>>,
    query: web::Query<HashMap<String, String>>,
) -> impl Responder {
    let db = db.lock().unwrap();
    let element = match query.get("元素") {
        Some(s) => s.clone(),
        None => {
            return HttpResponse::BadRequest().json(ApiResponse::<()> {
                success: false,
                message: Some("缺少查询参数 元素".to_string()),
                data: None,
            });
        }
    };
    let mut conditions = HashMap::new();
    conditions.insert("元素".to_string(), serde_json::Value::String(element));
    let ok = db.delete("compounds", conditions);
    HttpResponse::Ok().json(ApiResponse::<()> {
        success: ok,
        message: Some(if ok { "删除成功" } else { "未找到匹配记录" }.to_string()),
        data: None,
    })
}

#[actix_web::main]
async fn main() -> std::io::Result<()> {
    let mut db = FileDatabase::new("test_data");

    let mut wechat_columns = HashMap::new();
    wechat_columns.insert("openid".to_string(), "string".to_string());
    wechat_columns.insert("nickname".to_string(), "string".to_string());
    wechat_columns.insert("avatar".to_string(), "string".to_string());
    wechat_columns.insert("phone".to_string(), "string".to_string());
    wechat_columns.insert("create_time".to_string(), "integer".to_string());
    db.create_table("wechat_users", wechat_columns);

    let mut user_columns = HashMap::new();
    user_columns.insert("username".to_string(), "string".to_string());
    user_columns.insert("password_hash".to_string(), "string".to_string());
    user_columns.insert("email".to_string(), "string".to_string());
    user_columns.insert("phone".to_string(), "string".to_string());
    user_columns.insert("create_time".to_string(), "integer".to_string());
    db.create_table("users", user_columns);

    let mut compound_columns = HashMap::new();
    compound_columns.insert("元素".to_string(), "string".to_string());
    compound_columns.insert("备注".to_string(), "string".to_string());
    compound_columns.insert("晶体结构".to_string(), "string".to_string());
    compound_columns.insert("晶格常数".to_string(), "string".to_string());
    compound_columns.insert("晶格常数k".to_string(), "string".to_string());
    compound_columns.insert("etmx".to_string(), "string".to_string());
    compound_columns.insert("RESULT".to_string(), "string".to_string());
    compound_columns.insert("杨氏模量理论值".to_string(), "string".to_string());
    compound_columns.insert("杨氏模量E-H".to_string(), "string".to_string());
    compound_columns.insert("体积模量理论值".to_string(), "string".to_string());
    compound_columns.insert("治松比理论值".to_string(), "string".to_string());
    compound_columns.insert("弹性刚度理论值".to_string(), "string".to_string());
    compound_columns.insert("弹性刚度常数C11".to_string(), "string".to_string());
    compound_columns.insert("C12".to_string(), "string".to_string());
    compound_columns.insert("C44".to_string(), "string".to_string());
    compound_columns.insert("C33".to_string(), "string".to_string());
    compound_columns.insert("C13".to_string(), "string".to_string());
    db.create_table("compounds", compound_columns);

    // 使用同一个 db 实例，保证内存中的表结构被服务使用
    let db = web::Data::new(Mutex::new(db));

    HttpServer::new(move || {
        let cors = Cors::permissive();
        App::new()
            .wrap(cors)
            .app_data(db.clone())
            .route("/health", web::get().to(health))
            .route("/register", web::post().to(register))
            .route("/login", web::post().to(login))
            .route("/auth/verify", web::get().to(auth_verify))
            .route("/users/info", web::get().to(users_info))
            .route("/users/update", web::put().to(users_update))
            .route("/compounds", web::get().to(compounds_list))
            .route("/compounds", web::post().to(compounds_insert))
            .route("/compounds", web::put().to(compounds_update))
            .route("/compounds", web::delete().to(compounds_delete))
            .route("/compounds/query", web::post().to(compounds_query))
    })
    .bind(("127.0.0.1", 8088))?
    .run()
    .await
}
