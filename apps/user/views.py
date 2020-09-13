from django.conf import settings

from django.contrib.auth import authenticate, login, logout

from django.core.mail import send_mail
from django.core.urlresolvers import reverse

# 分页
from django.core.paginator import Paginator

from django.http import HttpResponse
from django.shortcuts import render,redirect
# from django.urls import reverse

from django.views.generic import View

import re

from django_redis import get_redis_connection

from .models import *

# 加密
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer
from itsdangerous import SignatureExpired # 异常

# 异步发送邮件
from celery_tasks.tasks import send_register_active_email

from utils.mixin import LoginRequiredMixin

from goods.models import GoodsSKU
from order.models import OrderInfo,OrderGoods

# Create your views here.


def register(request):
    if request.method == 'GET':
        return render(request,'register.html')
    else:
        '''进行注册处理'''
        # 接收数据
        username = request.POST.get('user_name')
        password = request.POST.get('pwd')
        email = request.POST.get('email')
        allow = request.POST.get('allow')
        # 进行数据校验 判断数据是否都传入
        if not all([username, email, password]):
            # 数据不完整
            return render(request, 'register.html', {'errmsg': '数据不完整'})
        # 校验邮箱
        if not re.match(r'^[a-z0-9][\w.\-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$', email):
            return render(request, 'register.html', {'errmsg': '邮箱格式不正确'})
        # 是否同意协议
        if allow != 'on':
            return render(request, 'register.html', {'errmsg': '请同意协议'})
        # 校验用户名是否重复
        try:
            user = User.objects.get(username=username)
            # 不存在会产生User.DoesNotExist异常
        except User.DoesNotExist:
            # 用户名不存在
            user = None

        if user:
            # 用户名已存在
            return render(request, 'register.html', {'errmsg': '用户名已存在'})
        # 进行业务处理: 进行用户注册
        # user = User.objects.create_user(username, email, password)
        user = User.objects.create_user(username, email, password)
        # 把django默认激活状态改为不激活
        user.is_active = 0
        user.save()
        # 返回应答, 跳转到首页
        return redirect(reverse('goods:index'))

def register_handle(request):
    '''进行注册处理'''
    # 接收数据
    username = request.POST.get('user_name')
    password = request.POST.get('pwd')
    email = request.POST.get('email')
    allow = request.POST.get('allow')
    # 进行数据校验 判断数据是否都传入
    if not all([username,email,password]):
        # 数据不完整
        return render(request, 'register.html', {'errmsg': '数据不完整'})
    # 校验邮箱
    if not re.match(r'^[a-z0-9][\w.\-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$', email):
        return render(request, 'register.html', {'errmsg':'邮箱格式不正确'})
    # 是否同意协议
    if allow != 'on':
        return render(request, 'register.html', {'errmsg':'请同意协议'})
    # 校验用户名是否重复
    try:
        user = User.objects.get(username=username)
        # 不存在会产生User.DoesNotExist异常
    except User.DoesNotExist:
        # 用户名不存在
        user = None

    if user:
        # 用户名已存在
        return render(request, 'register.html', {'errmsg': '用户名已存在'})
    # 进行业务处理: 进行用户注册
    # user = User.objects.create_user(username, email, password)
    user = User.objects.create_user(username, email, password)
    # 把django默认激活状态改为不激活
    user.is_active = 0
    user.save()
    # 返回应答, 跳转到首页
    return redirect(reverse('goods:index'))


# 类视图 # /user/register
class RegisterView(View):
    '''注册'''
    # 当请求是get的时候,调用get函数
    def get(self, request):
        '''显示注册页面'''
        return render(request, 'register.html')

    # 当请求是post的时候
    def post(self, request):
        '''进行注册处理'''
        # 接收数据
        username = request.POST.get('user_name')
        password = request.POST.get('pwd')
        email = request.POST.get('email')
        allow = request.POST.get('allow')

        # 判断密码
        if password != request.POST.get('cpwd'):
            return render(request,'register.html',{'errmsg':"两次密码不一致"})

    # 进行数据校验
        if not all([username, password, email]):
            # 数据不完整
            return render(request, 'register.html', {'errmsg': '数据不完整'})

        # 校验邮箱
        if not re.match(r'^[a-z0-9][\w.\-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$', email):
            return render(request, 'register.html', {'errmsg': '邮箱格式不正确'})

        if allow != 'on':
            return render(request, 'register.html', {'errmsg': '请同意协议'})

        # 校验用户名是否重复
        try:
            user = User.objects.get(username=username)
            # 不存在会产生User.DoesNotExist异常
        except User.DoesNotExist:
            # 用户名不存在
            user = None

        if user:
            # 用户名已存在
            return render(request, 'register.html', {'errmsg': '用户名已存在'})

        # 进行业务处理: 进行用户注册
        user = User.objects.create_user(username, email, password)
        user.is_active = 0 # 刚注册的用户是不激活的
        user.save()

        # 发送激活邮件，包含激活链接: http://176.136.5.66:8000/user/active/3(用户id)
        # 激活链接中需要包含用户的身份信息, 并且要把身份信息进行加密

        # 加密用户的身份信息，生成激活token口令  秘钥,过期时间
        serializer = Serializer(settings.SECRET_KEY, 3600)
        info = {'confirm':user.id}
        # 加密
        token = serializer.dumps(info) # bytes
        token = token.decode()
        # href = "http://176.136.5.66:8000/user/active/{}".format(token)

        # 发邮件
        # subject = '天天生鲜欢迎信息' # 标题
        # message = 'hello!%s' % username # 正文
        # sender = settings.EMAIL_FROM # 发送者
        # receiver = [email] # 收件人邮箱列表
        # html_message = '<h1>%s,欢迎您成为天天的会员</h1>请点击以下链接进行验证<p>\
        # <a href=%s>%s</p>' % (username,href,href)
        # send_mail(subject,message,sender,receiver,html_message=html_message)

        # 异步处理发送邮件,不会阻塞,提高用户体验
        # 导入celery_tasks中的发送邮件函数,放入redis任务队列中,发送注册激活邮件
        send_register_active_email.delay(email, username, token)

        # 返回应答, 跳转到首页
        return redirect(reverse('goods:index'))
        # return redirect(reverse('index'))




# 用户激活的视图类
class ActiveView(View):
    '''用户激活'''
    def get(self, request, token):
        '''进行用户激活'''
        # 进行解密，获取要激活的用户信息
        serializer = Serializer(settings.SECRET_KEY, 300)
        # 过期会抛出异常
        try:
            info = serializer.loads(token)
            # 获取待激活用户的id  info为字典
            user_id = info['confirm']
            # 根据id获取用户信息
            user = User.objects.get(id=user_id)
            user.is_active = 1
            user.save() # 保存
            # 激活成功 跳转到登录页面
            return redirect(reverse('user:login'))  # 反向解析
        except SignatureExpired as e:
            # 激活链接已过期  实际项目中应该再发送一个激活链接
            return HttpResponse('激活链接已过期')

# /user/login
class LoginView(View):
    '''登录'''
    def get(self, request):
        '''显示登录页面'''
        # 判断是否记住了用户名
        if 'username' in request.COOKIES:
            username = request.COOKIES.get('username')
            checked = 'checked'
        else:
            username = ''
            checked = ''
        # 获取请求的源地址
        print('源地址')
        origin_url = request.META.get('HTTP_REFERER', reverse('goods:index'))
        print(origin_url)
        # 将原地址添加到session中
        request.session['origin_url'] = origin_url
        # 使用模板
        return render(request, 'login.html',locals())

    def post(self, request):
        '''登录校验'''
        # 接收数据
        username = request.POST.get('username')
        password = request.POST.get('pwd')

        # 校验数据
        if not all([username, password]):
            return render(request, 'login.html', {'errmsg':'数据不完整'})

        # 业务处理:登录校验 django自带类进行校验
        # user = User.objects.get(username=username)
        # user.is_active = 1
        # user.save()
        # authenticate得到的是user对象
        user = authenticate(username=username, password=password)
        # user为None表示用户名密码错误
        print(username,password)
        print(type(user))

        if user is not None:
            # 用户名密码正确
            if user.is_active:
                # 用户已激活
                # 记录用户的登录状态,判断用户是否登录,把用户信息自动保存到session中
                login(request, user)
                # 获取请求的源地址
                origin_url = request.session['origin_url']
                # 获取登录后所要跳转到的地址,默认跳转到首页
                # next_url = request.GET.get('next','/')
                next_url = request.GET.get('next',origin_url)
                print(next_url)
                # 跳转到上一个页面
                response = redirect(next_url)

                # 判断是否需要记住用户名
                remember = request.POST.get('remember')
                # 得到复选框的值
                if remember == 'on':
                    # 记住用户名
                    response.set_cookie('username', username, max_age=60*60*24*7)
                else:
                    response.delete_cookie('username')

                # 返回response
                return response
            else:
                # 用户未激活,在次发送邮件给用户
                email = user.email
                info = {"confirm":user.id}
                # 创建加密对象
                serializer = Serializer(settings.SECRET_KEY, 300)
                # 加密
                token = serializer.dumps(info)  # bytes
                token = token.decode()
                send_register_active_email.delay(email, username, token)
                return render(request, 'login.html', {'errmsg':'账户未激活,请先激活'})
        else:
            # 用户名或密码错误
            return render(request, 'login.html', {'errmsg':'用户名或密码错误'})

# user/logout
class LogoutView(View):
    '''退出登录'''
    def get(self, request):
        '''退出登录'''
        # 清除用户的session信息
        logout(request)
        # 跳转到首页
        return redirect(reverse('goods:index'))


# 需要用户登录才能显示的页面
class UserInfoView(LoginRequiredMixin,View):
    def get(self,request):
        '''用户中心-信息页'''
        '''显示'''
        # Django会给request对象添加一个属性request.user
        # 如果用户未登录->user是AnonymousUser类的一个实例对象
        # 如果用户登录->user是User类的一个实例对象
        # request.user.is_authenticated()
        #
        # 获取用户的个人信息
        user = request.user
        # 获取默认地址
        address = Address.objects.get_default_address(user)
        # 获取用户的历史浏览记录

        # from redis import StrictRedis
        # # 创建对象
        # sr = StrictRedis(host='127.0.0.1', port='6379', db=9)
        # 获取连接redis数据库的对象 也就是StrictRedis的对象
        con = get_redis_connection('default')

        # history = history_key:[1,2,3..]
        history_key = 'history_%d' % user.id
        # 获取用户最新浏览的5个商品的id   lrange key start stop
        sku_ids = con.lrange(history_key, 0, 4) # 返回列表[2,3,1]
        # 从数据库中查询用户浏览的商品的具体信息
        # goods_li = GoodsSKU.objects.filter(id__in=sku_ids) # 得到列表
        # goods_res = []
        # for a_id in sku_ids:
        #     for goods in goods_li:
        #         if a_id == goods.id:
        #             goods_res.append(goods)
        # 遍历获取用户浏览的商品信息
        goods_li = []
        for id in sku_ids:
            goods = GoodsSKU.objects.get(id=id)
            goods_li.append(goods)

        # 组织上下文
        context = {'page':'user',
                   'address':address,
                   'goods_li':goods_li}

        # 除了你给模板文件传递的模板变量之外，django框架会把request.user也传给模板文件,
        # 模板可以直接使用user.is_authenticated
        return render(request, 'user_center_info.html',context)


# /user/order
class UserOrderView(LoginRequiredMixin, View):
    '''用户中心-订单页'''
    def get(self, request,page):
        '''显示'''
        # 获取用户的所有订单信息
        user = request.user                           # 降序显示订单信息
        orders = OrderInfo.objects.filter(user=user).order_by('-create_time')

        # 遍历获取订单商品信息
        for order in orders:
            # 根据order_id查询一个订单中所有商品的信息
            order_skus = OrderGoods.objects.filter(order_id=order.order_id)

            # 遍历order_skus计算商品的小计
            for order_sku in order_skus:
                price = order_sku.price
                count = order_sku.count
                # 计算小计
                amount = price * count
                # 动态给order_sku增减属性amount.保存订单商品的小计
                order_sku.amount = amount

            # 动态给order增加属性,保存订单状态文字标题
            order.status_name = OrderInfo.ORDER_STATUS[order.order_status]
            # 动态给order增加属性,保存订单商品的信息
            order.order_skus = order_skus

        # 分页 把orders对象传入 创建paginator对象
        paginator = Paginator(orders,1)

        # 处理页码
        try:
            page = int(page)
        except Exception as e:
            page = 1

        if page > paginator.num_pages:
            page = 1

        # 获取地page页的Page实例对象
        order_page = paginator.page(page)
        # todo:进行页码的控制 页面上最多最多显示5个页码
        # 1.总页数小于5页 页面上显示所有页
        # 2.如果当前页是前三页　显示1-5
        # 3.如果当前页是最后三页　显示后5页
        # 4.其他情况　显示当前页的前2页　当前页　后2页
        num_pages = paginator.num_pages
        if num_pages < 5:
            pages = range(1,num_pages+1)
        elif page < 3:
            pages = range(1,6)
        elif num_pages - page <= 2:
            pages = range(num_pages-4,num_pages+1)
        else:
            pages = range(page-2,page+3)

        # 组织上下文
        context ={
            'order_page':order_page,
            'pages':pages,
            'page':'order'
        }
        # 使用模板
        return render(request, 'user_center_order.html', context)


# 需要用户登录才能显示的页面
# /user 用户中心-个人信息
# class UserInfoView(LoginRequiredMixin, View):
#     '''用户中心-信息页'''
#     def get(self, request):
#         '''显示'''
        # Django会给request对象添加一个属性request.user
        # 如果用户未登录->user是AnonymousUser类的一个实例对象
        # 如果用户登录->user是User类的一个实例对象
        # request.user.is_authenticated()

        # 获取用户的个人信息
        # user = request.user
        # address = Address.objects.get_default_address(user)

        # 获取用户的历史浏览记录
        # from redis import StrictRedis
        # sr = StrictRedis(host='172.16.179.130', port='6379', db=9)
        # con = get_redis_connection('default')

        # history_key = 'history_%d'%user.id

        # 获取用户最新浏览的5个商品的id
        # sku_ids = con.lrange(history_key, 0, 4) # [2,3,1]

        # 从数据库中查询用户浏览的商品的具体信息
        # goods_li = GoodsSKU.objects.filter(id__in=sku_ids)
        #
        # goods_res = []
        # for a_id in sku_ids:
        #     for goods in goods_li:
        #         if a_id == goods.id:
        #             goods_res.append(goods)

        # 遍历获取用户浏览的商品信息
        # goods_li = []
        # for id in sku_ids:
        #     goods = GoodsSKU.objects.get(id=id)
        #     goods_li.append(goods)
        #
        # # 组织上下文
        # context = {'page':'user',
        #            'address':address,
        #            'goods_li':goods_li}

        # 除了你给模板文件传递的模板变量之外，django框架会把request.user也传给模板文件,
        # 模板可以直接使用user.is_authenticated
        # return render(request, 'user_center_info.html')




# /user/address
class AddressView(LoginRequiredMixin,View):

    def get(self, request):
        '''显示'''
        # 获取登录用户对应User对象
        user = request.user
        # 获取用户的默认收货地址
        # try:
        #     address = Address.objects.get(user=user, is_default=True)  # models.Manager
        # except Address.DoesNotExist:
        #     # 不存在默认收货地址
        #     address = None
        address = Address.objects.get_default_address(user) # 模型管理器类

        # 使用模板
        return render(request, 'user_center_site.html', {'page': 'address', 'address': address})

    def post(self, request):
        '''地址的添加'''
        # 接收数据
        receiver = request.POST.get('receiver')
        addr = request.POST.get('addr')
        zip_code = request.POST.get('zip_code') # 可以为空
        phone = request.POST.get('phone')

        # 校验数据 判断数据是否齐全
        if not all([receiver, addr, phone, type]):
            return render(request, 'user_center_site.html', {'errmsg':'数据不完整'})

        # 校验手机号是否正确
        if not re.match(r'^1[3|4|5|7|8][0-9]{9}$', phone):
            return render(request, 'user_center_site.html', {'errmsg':'手机格式不正确'})

        # 业务处理：地址添加
        # 如果用户已存在默认收货地址，添加的地址不作为默认收货地址，否则作为默认收货地址
        # 如果用户已经登录,则获取的是登录用户对应User对象
        user = request.user
        # try:
        #     address = Address.objects.get(user=user, is_default=True)# 有默认地址
        # except Address.DoesNotExist:
        #     # 不存在默认收货地址
        #     address = None
        address = Address.objects.get_default_address(user)

        if address: # 表明用户已经有了默认收获的地址,那么新创建的的地址不能设为默认的收货地址
            is_default = False
        else:
            is_default = True # 不存在默认收货地址,则把新增的地址设置为默认地址

        # 添加地址
        Address.objects.create(user=user,
                               receiver=receiver,
                               addr=addr,
                               zip_code=zip_code,
                               phone=phone,
                               is_default=is_default)

        # 返回应答,重定向来刷新地址页面,可以看到新增的默认收货地址
        return redirect(reverse('user:address')) # get请求方式









