use serde::{Deserialize, Serialize};
use serde_json::{from_reader, to_writer_pretty};
use std::collections::HashMap;
use std::fs::{self, File};
use std::io::{BufReader, BufWriter};
use std::path::Path;
use csv::ReaderBuilder;

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct TableSchema {
    pub columns: HashMap<String, String>, // 列名 -> 类型
    pub columns_order: Vec<String>,      // 字段顺序
    pub created_at: u64,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct DatabaseSchema {
    pub tables: HashMap<String, TableSchema>,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct FileDatabase {
    pub db_path: String,
    pub schema: DatabaseSchema,
}

impl FileDatabase {
    pub fn new(db_path: &str) -> Self {
        let schema = Self::load_schema(db_path);
        FileDatabase {
            db_path: db_path.to_string(),
            schema,
        }
    }

    fn schema_file(&self) -> String {
        format!("{}/schema.json", self.db_path)
    }

    fn table_file(&self, table_name: &str) -> String {
        format!("{}/{}.json", self.db_path, table_name)
    }

    fn load_schema(db_path: &str) -> DatabaseSchema {
        let schema_path = format!("{}/schema.json", db_path);
        if Path::new(&schema_path).exists() {
            let file = File::open(&schema_path).unwrap();
            let reader = BufReader::new(file);
            serde_json::from_reader(reader).unwrap_or(DatabaseSchema {
                tables: HashMap::new(),
            })
        } else {
            DatabaseSchema {
                tables: HashMap::new(),
            }
        }
    }

    fn save_schema(&self) {
        fs::create_dir_all(&self.db_path).unwrap();
        let file = File::create(self.schema_file()).unwrap();
        let writer = BufWriter::new(file);
        to_writer_pretty(writer, &self.schema).unwrap();
    }

    pub fn create_table(&mut self, table_name: &str, columns: HashMap<String, String>) -> bool {
        if self.schema.tables.contains_key(table_name) {
            return false;
        }
        let columns_order: Vec<String> = columns.keys().cloned().collect();
        let schema = TableSchema {
            columns,
            columns_order,
            created_at: chrono::Utc::now().timestamp() as u64,
        };
        self.schema.tables.insert(table_name.to_string(), schema);
        self.save_schema();
        // 创建空数据文件
        let file = File::create(self.table_file(table_name)).unwrap();
        let writer = BufWriter::new(file);
        to_writer_pretty(writer, &Vec::<HashMap<String, serde_json::Value>>::new()).unwrap();
        true
    }

    #[allow(dead_code)]
    pub fn drop_table(&mut self, table_name: &str) -> bool {
        if !self.schema.tables.contains_key(table_name) {
            return false;
        }
        self.schema.tables.remove(table_name);
        self.save_schema();
        let table_path = self.table_file(table_name);
        if Path::new(&table_path).exists() {
            fs::remove_file(table_path).unwrap();
        }
        true
    }

    pub fn insert(&self, table_name: &str, data: HashMap<String, serde_json::Value>) -> bool {
        if !self.schema.tables.contains_key(table_name) {
            return false;
        }
        let mut table_data = self.load_table_data(table_name);
        table_data.push(data);
        self.save_table_data(table_name, &table_data);
        true
    }

    pub fn select(&self, table_name: &str, conditions: Option<HashMap<String, serde_json::Value>>) -> Vec<HashMap<String, serde_json::Value>> {
        if !self.schema.tables.contains_key(table_name) {
            return vec![];
        }
        let table_data = self.load_table_data(table_name);
        if let Some(conds) = conditions {
            table_data
                .into_iter()
                .filter(|row| {
                    conds.iter().all(|(k, v)| row.get(k) == Some(v))
                })
                .collect()
        } else {
            table_data
        }
    }

    pub fn update(&self, table_name: &str, conditions: HashMap<String, serde_json::Value>, new_data: HashMap<String, serde_json::Value>) -> bool {
        if !self.schema.tables.contains_key(table_name) {
            return false;
        }
        let mut table_data = self.load_table_data(table_name);
        let mut updated = false;
        for row in &mut table_data {
            if conditions.iter().all(|(k, v)| row.get(k) == Some(v)) {
                for (k, v) in &new_data {
                    row.insert(k.clone(), v.clone());
                }
                updated = true;
            }
        }
        self.save_table_data(table_name, &table_data);
        updated
    }

    pub fn delete(&self, table_name: &str, conditions: HashMap<String, serde_json::Value>) -> bool {
        if !self.schema.tables.contains_key(table_name) {
            return false;
        }
        let mut table_data = self.load_table_data(table_name);
        let original_len = table_data.len();
        table_data.retain(|row| !conditions.iter().all(|(k, v)| row.get(k) == Some(v)));
        let changed = table_data.len() < original_len;
        self.save_table_data(table_name, &table_data);
        changed
    }

    fn load_table_data(&self, table_name: &str) -> Vec<HashMap<String, serde_json::Value>> {
        let table_path = self.table_file(table_name);
        if Path::new(&table_path).exists() {
            let file = File::open(table_path).unwrap();
            let reader = BufReader::new(file);
            from_reader(reader).unwrap_or(Vec::new())
        } else {
            Vec::new()
        }
    }

    fn save_table_data(&self, table_name: &str, data: &Vec<HashMap<String, serde_json::Value>>) {
        let file = File::create(self.table_file(table_name)).unwrap();
        let writer = BufWriter::new(file);
        to_writer_pretty(writer, data).unwrap();
    }

    /// 清空表数据
    #[allow(dead_code)]
    pub fn clear_table(&self, table_name: &str) -> bool {
        if !self.schema.tables.contains_key(table_name) {
            return false;
        }
        let file = File::create(self.table_file(table_name)).unwrap();
        let writer = BufWriter::new(file);
        to_writer_pretty(writer, &Vec::<HashMap<String, serde_json::Value>>::new()).unwrap();
        true
    }

    /// 从CSV文件导入数据到指定表，并保存字段顺序
    #[allow(dead_code)]
    pub fn import_from_csv(&mut self, table_name: &str, csv_path: &str, delimiter: u8) -> bool {
        if !self.schema.tables.contains_key(table_name) {
            return false;
        }
        let file = match File::open(csv_path) {
            Ok(f) => f,
            Err(e) => {
                eprintln!("无法打开CSV文件: {}", e);
                return false;
            }
        };
        let mut rdr = ReaderBuilder::new()
            .delimiter(delimiter)
            .from_reader(file);
        let headers = match rdr.headers() {
            Ok(h) => h.clone(),
            Err(e) => {
                eprintln!("读取CSV表头失败: {}", e);
                return false;
            }
        };
        // 保存字段顺序到schema
        if let Some(schema) = self.schema.tables.get_mut(table_name) {
            schema.columns_order = headers.iter().map(|s| s.to_string()).collect();
            // 自动补全columns类型为string（如需更精细可后续完善）
            for col in &schema.columns_order {
                schema.columns.entry(col.clone()).or_insert("string".to_string());
            }
            self.save_schema();
        }
        let mut success = true;
        let mut table_data = Vec::new();
        for result in rdr.records() {
            match result {
                Ok(record) => {
                    let mut row = HashMap::new();
                    for (i, field) in record.iter().enumerate() {
                        let key = headers.get(i).unwrap_or("").to_string();
                        let value = if let Ok(num) = field.parse::<i64>() {
                            serde_json::Value::from(num)
                        } else if let Ok(flt) = field.parse::<f64>() {
                            serde_json::Value::from(flt)
                        } else {
                            serde_json::Value::from(field)
                        };
                        row.insert(key, value);
                    }
                    table_data.push(row);
                }
                Err(e) => {
                    eprintln!("读取CSV行失败: {}", e);
                    success = false;
                    break;
                }
            }
        }
        // 覆盖写入表数据
        self.save_table_data(table_name, &table_data);
        success
    }

    /// 查询数据，按columns_order顺序输出（如有）
    #[allow(dead_code)]
    pub fn select_ordered(&self, table_name: &str, conditions: Option<HashMap<String, serde_json::Value>>) -> Vec<Vec<(String, serde_json::Value)>> {
        if !self.schema.tables.contains_key(table_name) {
            return vec![];
        }
        let schema = &self.schema.tables[table_name];
        let table_data = self.select(table_name, conditions);
        let mut result = Vec::new();
        for row in table_data {
            let mut ordered_row = Vec::new();
            for col in &schema.columns_order {
                if let Some(val) = row.get(col) {
                    ordered_row.push((col.clone(), val.clone()));
                } else {
                    ordered_row.push((col.clone(), serde_json::Value::Null));
                }
            }
            result.push(ordered_row);
        }
        result
    }
}

/*
依赖项：
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"
chrono = "0.4"
csv = "1.3"

本实现已兼容Linux和Windows系统，路径分隔符建议统一使用'/'。
*/ 