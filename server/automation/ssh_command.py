import paramiko
from tqdm import tqdm
import time  # 用于模拟长时间运行的操作

def ssh_connect(hostname, port, username, password):  # 连接服务器
    """
    创建SSH连接
    """
    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh_client.connect(hostname, port, username, password)
        print("成功连接服务器")  # 添加调试信息
        return ssh_client  # 返回SSHClient对象
    except Exception as e:
        print(f"连接失败: {str(e)}")  # 打印错误信息
        return None  # 返回None表示连接失败


def main():
    # 在这里添加测试代码或示例代码
    hostname = '222.199.219.3'
    port = 22
    username = 'yyj'
    password = '111111'

    # 测试连接
    ssh_client = ssh_connect(hostname, port, username, password)
    if ssh_client:
        print("连接成功，可以执行其他操作")
        ssh_client.close()  # 关闭连接


def ssh_execute_commands(ssh_client, commands):  # 执行命令
    """
    执行多个SSH命令
    """
    results = []  # 用于存储每个命令的输出
    for command in tqdm(commands, desc="执行命令", unit="命令"):
        stdin, stdout, stderr = ssh_client.exec_command(command)
        result = stdout.read().decode('utf-8')
        error = stderr.read().decode('utf-8')
        if error:
            results.append(f"Error executing '{command}': {error}")
        else:
            results.append(f"Output of '{command}': {result}")
    return results  # 返回所有命令的输出

def ssh_change_directory(ssh_client, directory):  # 切换目录
    """
    切换SSH会话的当前工作目录
    """
    stdin, stdout, stderr = ssh_client.exec_command(f'cd {directory} && pwd')
    result = stdout.read().decode('utf-8')
    error = stderr.read().decode('utf-8')
    if error:
        print(f"Error changing directory to '{directory}': {error}")
    else:
        print(f"Changed directory to '{directory}': {result}")

def ssh_copy_paste(ssh_client, source_path, destination_path):  # 模拟复制粘贴
    """
    模拟复制粘贴操作
    """
    # 这里只是模拟复制粘贴操作，实际的复制粘贴操作需要在终端模拟器中完成
    commands = [
        f'cp {source_path} {destination_path}',  # 复制文件
        f'ls {destination_path}'  # 列出目标目录下的文件以验证复制操作
    ]
    ssh_execute_commands(ssh_client, commands)

def execute_ssh_command(command_name, *args):
    print(f"Executing command: {command_name}, with args: {args}")  # 添加调试信息
    if command_name == 'ssh_connect':
        if len(args) < 4:  # 确保有足够的参数
            return "缺少必要的参数"  # 返回错误信息
        ssh_client = ssh_connect(*args[:4])  # 获取SSHClient对象
        if ssh_client is None:
            return "连接失败"  # 如果连接失败，返回错误信息
        return "成功连接服务器"  # 返回成功消息
    elif command_name == 'ssh_execute_commands':
        ssh_client = ssh_connect(*args[:4])  # 使用前四个参数重新连接SSH
        if ssh_client is None:
            return "连接失败"
        command = args[4]  # 获取命令
        return ssh_execute_commands(ssh_client, [command])
    elif command_name == 'ssh_change_directory':
        ssh_client = ssh_connect(*args[:4])  # 使用前四个参数重新连接SSH
        if ssh_client is None:
            return "连接失败"
        return ssh_change_directory(ssh_client, *args[4:])
    elif command_name == 'ssh_copy_paste':
        ssh_client = ssh_connect(*args[:4])  # 使用前四个参数重新连接SSH
        if ssh_client is None:
            return "连接失败"
        return ssh_copy_paste(ssh_client, *args[4:])
    else:
        return "Unknown command"


def execute_workflow(ssh_client, element, lattice_constants,a,b,c):
    """
    执行完整的工作流程
    """
    # 创建新文件夹
    command_mkdir = f'mkdir -p DATA3/{element}'  # 创建新文件夹 new_folder
    ssh_execute_commands(ssh_client, [command_mkdir])
    directory = 'DATA3/{}'.format(element)

    # 复制文件到运行目录
    ssh_copy_paste(ssh_client, 'job_sbatch_1.sh', './')
    ssh_copy_paste(ssh_client, 'job_sbatch_2.sh', './')

    # 初始结构生成
    input_generate_command = "python ~/HTEM/source/HTEM.py input_generate -b {} {} {} {} {} -k 0.10".format(lattice_constants,element,a,b,c)
    ssh_execute_commands(ssh_client, [input_generate_command])

    #基本结构分类
    if lattice_constants == 'fcc':
        na_value=4
        symmetry= 'C'
    elif lattice_constants == 'bcc':
        na_value=2
        symmetry= 'C'
    elif lattice_constants == 'hcp':
        na_value = 2
        symmetry = 'H'

    # 初始结构弛豫计算
    relax1_command = "python ~/HTEM/source/HTEM.py relax1 -nv 1 -na {}".format(int(na_value))
    ssh_execute_commands(ssh_client, [relax1_command, './job_sbatch_1.sh'])

    # 应变结构生成
    create_command = "python ~/HTEM/source/HTEM.py create -lt {} -etmx 0.03 -ns 9".format(symmetry)
    ssh_execute_commands(ssh_client, [create_command])

    # 应变结构弛豫计算
    relax2_command = "python ~/HTEM/source/HTEM.py relax2"
    ssh_execute_commands(ssh_client, [relax2_command, './job_sbatch_2.sh'])

    # 应变结构静态计算
    static_command = "python ~/HTEM/source/HTEM.py static"
    ssh_execute_commands(ssh_client, [static_command, './job_sbatch_2.sh'])

    # 结果分析
    analyze_command = "python ~/HTEM/source/HTEM.py analyze"
    ssh_execute_commands(ssh_client, [analyze_command])

    # 查看结果文件
    ssh_execute_commands(ssh_client, ["cat ElasticTinf.out"])

#yyj修改
def fixed_workflow(ssh_client, element, lattice_constants,a,b,c):
    #输入元素参数
    element=input()
    lattice_constants=input()
    if lattice_constants=='fcc' or 'bcc':
        a=float(input())
        b=a
        c=a
    elif lattice_constants=='hcp':
        a=float(input())
        b=a
        c=float(input())



def test():
    # 设置SSH服务器的IP地址、端口、用户名和密码
    hostname = '222.199.219.3'
    port = 22  # SSH端口，默认是22
    username = 'yyj'
    password = '111111'

    # 连接SSH服务器
    ssh_client = ssh_connect(hostname, port, username, password)

    try:
        # 切换目录
        #ssh_change_directory(ssh, '/path/to/directory')

        # 执行命令
        change_sudoers = 'echo "yyj ALL=(ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/yyj <<< 111111'  # 添加yyj用户到sudoers文件
        download_numpy = '''
        wget --no-check-certificate -P /home/yyj https://github.com/numpy/numpy/archive/refs/tags/v1.23.5.zip
        '''  # 下载numpy源代码

        #execute_workflow(ssh_client, element, lattice_constants, a, b, c)

        htem_command = '/home/cj/.conda/envs/HTEM/bin/python3 ~/HTEM/source/HTEM.py input_generate -b fcc Al 3.5 3.5 3.5 -k 0.10'

        # 检查文件是否存在
        check_file = '''
        if [ -f numpy-1.23.5.zip ]; then
            echo "File exists, size: $(stat -c%s numpy-1.23.5.zip) bytes"
        else
            echo "File does not exist."
        fi
        '''

        # 解压numpy源代码
        unzip_numpy = '''
        unzip numpy-1.23.5.zip && \
        cd numpy-1.23.5
        '''  # 解压并进入目录

        # 其他命令
        commands = [htem_command]
        ssh_execute_commands(ssh_client, commands)

        # 模拟复制粘贴操作
        #ssh_copy_paste(ssh, '/path/to/source/file.txt', '/path/to/destination/')


    except Exception as e:
        print(f"Error: {e}")

    finally:
        # 关闭SSH连接
        ssh_client.close()

# 添加以下代码以确保只有在直接运行时才会调用 main 函数
if __name__ == "__main__":
    main()