# 使用celery
from django.core.mail import send_mail
from django.conf import settings
from celery import Celery
import time

from django.shortcuts import render
from django.template import loader
from django.views.generic import View
from django_redis import get_redis_connection



# 在任务处理者worker一端加这几句,django项目中可以不加
import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dailyfresh.settings")
django.setup() # django环境的初始化
# 写在初始化之后,不然找不到
from goods.models import *

# 创建一个Celery类的实例对象 参数(起个名字:一般起路径,中间人)  查看redis:ps aux | grep redis
app = Celery('celery_tasks.tasks', broker='redis://127.0.0.1:6379/8')


# 定义任务函数  发邮件任务
@app.task
def send_register_active_email(to_email, username, token):
    '''发送激活邮件'''
    # 组织邮件信息
    subject = '天天生鲜欢迎信息'  # 标题
    message = 'hello!%s' % username  # 正文
    sender = settings.EMAIL_FROM  # 发送者
    receiver = [to_email]  # 收件人邮箱列表
    href = "http://176.136.5.66:8000/user/active/{}".format(token)
    html_message = '<h1>%s,欢迎您成为天天的会员</h1>请点击以下链接进行验证,点击链接就可以激活邮箱，从而用邮箱进行登陆<p>\
            <a href=%s>%s,我们将为您提供更好的服务</p>' % (username, href, href)
    send_mail(subject, message, sender, receiver, html_message=html_message)
    time.sleep(5)

@app.task
def generate_static_index_html():
    '''产生首页静态页面'''
    # 获取商品的种类信息
    types = GoodsType.objects.all()

    # 获取首页轮播商品信息
    goods_banners = IndexGoodsBanner.objects.all().order_by('index')

    # 获取首页促销活动信息
    promotion_banners = IndexPromotionBanner.objects.all().order_by('index')

    # 获取首页分类商品展示信息
    for type in types:  # GoodsType
        # 获取type种类首页分类商品的图片展示信息
        image_banners = IndexTypeGoodsBanner.objects.filter(type=type, display_type=1).order_by('index')
        # 获取type种类首页分类商品的文字展示信息
        title_banners = IndexTypeGoodsBanner.objects.filter(type=type, display_type=0).order_by('index')

        # 动态给type增加属性，分别保存首页分类商品的图片展示信息和文字展示信息
        type.image_banners = image_banners
        type.title_banners = title_banners


    # 组织模板上下文
    context = {'types': types,
               'goods_banners': goods_banners,
               'promotion_banners': promotion_banners}

    # 使用模板
    # 1.加载模板文件,返回模板对象
    temp = loader.get_template('static_index.html')
    # 2.模板渲染
    static_index_html = temp.render(context)
    # 生成首页对应静态文件
    save_path = os.path.join(os.path.dirname(settings.BASE_DIR), 'DjangoProject/dailyfresh/static/index.html')
    print(save_path)
    # save_path = os.path.join(settings.BASE_DIR, 'static/index.html')
    with open(save_path, 'w') as f:
        f.write(static_index_html)























