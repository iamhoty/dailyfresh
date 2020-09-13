# 重新定义django的文件存储的类
from django.core.files.storage import Storage
# 导入fastdfs
from fdfs_client.client import Fdfs_client
from django.conf import settings

class FDFSStorage(Storage):
    '''文件存储类'''
    def __init__(self,client_conf=None,base_url=None):
        if client_conf is None:
            client_conf = settings.FDFS_CLIENT_CONF
        self.client_conf = client_conf
        if base_url is None:
            base_url = settings.FDFS_URL
        self.base_url = base_url

    def _open(self,name,mode='rb'):
        '''打开文件时使用'''
        pass

    def _save(self,name,content):
        '''保存文件时使用'''
        # name ： 你选择上传文件的名字
        # content : 包含你上传文件内容的File对象

        # 创建一个Fdfs_client的对象 路径是相对于dailyfresh该项目的路径
        client = Fdfs_client(self.client_conf)
        # 上传文件到fast dfs系统
        res = client.upload_by_buffer(content.read()) # 返回res为字典
        # dict
        # {
        #     'Group name': group_name,
        #     'Remote file_id': remote_file_id,
        #     'Status': 'Upload successed.',
        #     'Local file name': '',
        #     'Uploaded size': upload_size,
        #     'Storage IP': storage_ip
        # }
        if res.get('Status') != 'Upload successed.':
            # 上传失败
            raise Exception('上传文件到fast dfs失败')

        # 获取返回的文件ID
        filename = res.get('Remote file_id')

        return filename # 数据表中存储的名字

    def exists(self, name):
        '''Django判断文件名是否可用'''
        # 因为保存到fastdfs中,所以不涉及到django文件是否可用,所以返回false，表示一直可用
        return False

    def url(self, name): # name为数据表中存储的filename文件名
        '''返回访问文件的url路径'''
        return self.base_url + name
