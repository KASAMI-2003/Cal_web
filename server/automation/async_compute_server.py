from flask import Flask, request, jsonify
from celery import Celery
import time

# 创建 Flask 应用
app = Flask(__name__)

# 配置 Celery
app.config['CELERY_BROKER_URL'] = 'redis://localhost:6379/0'  # Redis 作为消息代理
app.config['CELERY_RESULT_BACKEND'] = 'redis://localhost:6379/0'  # Redis 作为结果存储
celery = Celery(app.name, broker=app.config['CELERY_BROKER_URL'])
celery.conf.update(app.config)

# 定义一个长时间运行的任务
@celery.task
def long_running_task(data):
    time.sleep(10)  # 模拟长时间运行的任务
    return f"处理完成: {data}"

# 启动任务的 API 端点
@app.route('/start_task', methods=['POST'])
def start_task():
    data = request.json.get('data')
    task = long_running_task.apply_async(args=[data])  # 异步执行任务
    return jsonify({'task_id': task.id}), 202

# 检查任务状态的 API 端点
@app.route('/task_status/<task_id>', methods=['GET'])
def task_status(task_id):
    task = long_running_task.AsyncResult(task_id)
    return jsonify({'state': task.state, 'result': task.result if task.state == 'SUCCESS' else None})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5101)
