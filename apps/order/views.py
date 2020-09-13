from datetime import datetime
import time
from django.core.urlresolvers import reverse
from django.db import transaction
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect
from django.conf import settings

# Create your views here.
from django.views.generic import View
from django_redis import get_redis_connection
from goods.models import GoodsSKU
from user.models import Address
from order.models import OrderInfo,OrderGoods

from utils.mixin import LoginRequiredMixin
from alipay import AliPay
import os

# /order/place 点击去结算跳转的页面
# 只传商品的id
# 不涉及到ajax　浏览器可以看到请求的效果 可以使用LoginRequiredMixin进行页面的跳转
class OrderPlaceView(LoginRequiredMixin,View):
    '''提交订单页面显示'''
    def post(self,request):
        '''提交订单页面显示'''
        # 获取登录的用户
        user = request.user
        if not user.is_authenticated():
            # 用户未登录返回到登录界面
            return redirect(reverse('user:login'))

        # 获取参数sku_ids checkbox用getlist来接收
        sku_ids = request.POST.getlist('sku_ids') # 返回来的是字符串列表

        # 校验参数
        if not sku_ids:
            # 如果sku_ids为False 反向解析跳转到购物车页面
            return redirect(reverse('cart:show'))


        conn = get_redis_connection('default')
        cart_key = 'cart_%d' % user.id
        # sku商品列表
        skus = []
        # 保存商品总价钱
        total_price = 0
        # 保存商品总件数
        total_count = 0
        # 遍历sku_ids获取用户要购买的商品信息
        for sku_id in sku_ids:
            # 根据商品的id获取商品的信息
            try:
                # sku_id是字符串 但是也可以进行查询
                sku = GoodsSKU.objects.get(id=sku_id)
            except GoodsSKU.DoesNotExist:
                # 商品id不存在
                return redirect(reverse('cart:show'))
            # 获取用户所要购买商品的数量 参数：购物车　商品id
            count = int(conn.hget(cart_key,sku_id))
            # 计算商品的小计
            amount = sku.price * count
            # 动态给sku对象增加count属性
            sku.count = count
            # 动态给sku对象增加amount属性 保存购买商品的小计
            sku.amount = amount
            # 把商品信息放入列表中 用于给前端　方便前端进行遍历
            skus.append(sku)
            # 累加计算商品的总件数
            total_count += count
            # 累加计算商品的总价格
            total_price += amount

        # 运费 实际开发的时候,属于一个专门计算运费的子系统
        # 这里我是写死的
        transit_price = 10

        # 实际付款
        total_pay = total_price + transit_price

        # 获取用户的收件地址 得到收获地址列表
        addrs = Address.objects.filter(user=user)
        # sku_ids是一个字符串列表
        sku_ids = ','.join(sku_ids) # 变成字符串
        # 组织上下文
        context = {'skus':skus,
                   'total_count':total_count,
                   'total_price':total_price,
                   'transit_price':transit_price,
                   'total_pay':total_pay,
                   'addrs':addrs}
        # 使用模板
        return render(request,'place_order.html',locals())

# 订单创建
# 传递参数:收获地址 支付方式 商品id(id以字符串的方式传入)
# 注意:传递参数时　是不会传递价钱的　防止前端页面的恶意更改
# todo:mysql事务: 一组sql操作，要么都成功，要么都失败
# 高并发:秒杀
# 支付宝支付
# /user/order/
class OrderCommitView1(View):
    '''订单创建'''
    @transaction.atomic # 数据库操作中事务的提交与回滚
    def post(self,request):
        # 判断用户是否登录
        user = request.user
        if not user.is_authenticated():
            # 用户未登录
            return JsonResponse({'res':0,"errmsg":'用户未登录!'})

        # 接收参数
        addr_id = request.POST.get('addr_id')
        pay_method = request.POST.get('pay_method')
        sku_ids = request.POST.get('sku_ids')

        # 判断数据是否完整
        if not all([addr_id,pay_method,sku_ids]):
            return JsonResponse({'res': 1, "errmsg": '参数不完整'})

        # 校验支付方式 判断支付方式的数字是否存在字典的键中
        if pay_method not in OrderInfo.PAY_METHODS.keys():
            return JsonResponse({'res': 2, "errmsg": '非法的支付方式'})

        # 校验收货地址
        try:
            addr = Address.objects.get(id=addr_id)
        except Address.DoesNotExist:
            # 地址不存在
            return JsonResponse({'res': 3, "errmsg": '地址不存在'})

        # 创建订单的业务处理
        # order_id total_count total_price transit_price   order_status trade_no这两个是默认的
        # user addr pay_method
        # 组织参数
        # 订单id order_id 年月日时分秒+用户id
        order_id = datetime.now().strftime('%Y%m%d%H%M%S') + str(user.id)

        # 运费
        transit_price = 10

        # 商品总数目和总金额
        total_count = 0
        total_price = 0

        # 设置事务的保存点 以下有对数据库的操作
        save_id = transaction.savepoint()
        # 捕获异常 看看对数据库的操作是否有异常 如果有异常回滚到保存点
        try:
            # todo:向df_order_info表中添加一条记录
            order = OrderInfo.objects.create(order_id=order_id,
                                             user=user,
                                             addr=addr,
                                             pay_method=pay_method,
                                             total_price=transit_price,
                                             total_count=total_count,
                                             transit_price=transit_price)

            # todo:用户订单中有几个商品　需要向df_order_goods表中加入几条数据
            # 给df_order_goods加记录　order sku count price comment
            conn = get_redis_connection('default')
            cart_key = 'cart_%d' % user.id
            sku_ids = sku_ids.split(',') # 将字符串变为字符串列表
            for sku_id in sku_ids:
                # 根据商品id sku_id 获取商品的信息
                try:
                    # 悲观锁 等到事务结束后会释放锁
                    # 加悲观锁 数据库操作select * from df_goods_sku where id=sku_id for update;
                    sku = GoodsSKU.objects.select_for_update().get(id=sku_id)
                    # sku = GoodsSKU.objects.get(id=sku_id)
                except GoodsSKU.DoesNotExist:
                    # 商品不存在
                    # 进行事务回滚 也就不会创建订单信息表
                    transaction.savepoint_rollback(save_id)
                    return JsonResponse({'res': 4, "errmsg": '商品不存在'})

                # 从redis中获取用户购买商品的数量
                count = int(conn.hget(cart_key,sku_id))

                # todo:判断商品的库存
                # 防止同一时间 其他用户购买商品 导致库存不足
                if count > sku.stock:
                    # 进行事务回滚 不创建订单信息表
                    transaction.savepoint_rollback(save_id)
                    return JsonResponse({'res': 6, "errmsg": '商品库存不足'})

                # todo:向df_order_goods添加一条记录  每一个商品都要添加订单商品
                OrderGoods.objects.create(order=order,
                                          sku=sku,
                                          count=count,
                                          price=sku.price)

                # 更新商品的库存和销量
                sku.stock -= count
                sku.sales += count

                # 更新
                sku.save()

                # todo:累加计算订单商品的总数目和总价格
                # 小计
                amount = sku.price * count
                total_count += count
                total_price += amount

            # todo:更新订单信息表中的总数量和总价格
            order.total_count = total_count
            order.total_price = total_price
            order.save()
        except Exception as e:
            # 捕获异常 并进行回滚
            transaction.savepoint_rollback(save_id)
            return JsonResponse({'res': 7, "errmsg": '下单失败'})

        # 没有问题 提交事务到数据库 释放悲观锁
        transaction.savepoint_commit(save_id)

        # todo:用户提交订单后 清除用户购物车中的记录
        # 从redis中删除商品列表 hdel(name,*keys)
        conn.hdel(cart_key,*sku_ids)

        return JsonResponse({'res': 5, "message": '创建订单成功'})

# 乐观锁
# /user/order/
class OrderCommitView(View):
    '''订单创建'''
    @transaction.atomic # 数据库操作中事务的提交与回滚
    def post(self,request):
        # 判断用户是否登录
        user = request.user
        if not user.is_authenticated():
            # 用户未登录
            return JsonResponse({'res':0,"errmsg":'用户未登录!'})

        # 接收参数
        addr_id = request.POST.get('addr_id')
        pay_method = request.POST.get('pay_method')
        sku_ids = request.POST.get('sku_ids')

        # 判断数据是否完整
        if not all([addr_id,pay_method,sku_ids]):
            return JsonResponse({'res': 1, "errmsg": '参数不完整'})

        # 校验支付方式 判断支付方式的数字是否存在字典的键中
        if pay_method not in OrderInfo.PAY_METHODS.keys():
            return JsonResponse({'res': 2, "errmsg": '非法的支付方式'})

        # 校验收货地址
        try:
            addr = Address.objects.get(id=addr_id)
        except Address.DoesNotExist:
            # 地址不存在
            return JsonResponse({'res': 3, "errmsg": '地址不存在'})

        # 创建订单的业务处理
        # order_id total_count total_price transit_price   order_status trade_no这两个是默认的
        # user addr pay_method
        # 组织参数
        # 订单id order_id 年月日时分秒+用户id
        order_id = datetime.now().strftime('%Y%m%d%H%M%S') + str(user.id)

        # 运费
        transit_price = 10

        # 商品总数目和总金额
        total_count = 0
        total_price = 0

        # 设置事务的保存点 以下有对数据库的操作
        save_id = transaction.savepoint()
        # 捕获异常 看看对数据库的操作是否有异常 如果有异常回滚到保存点
        try:
            # todo:向df_order_info表中添加一条记录
            order = OrderInfo.objects.create(order_id=order_id,
                                             user=user,
                                             addr=addr,
                                             pay_method=pay_method,
                                             total_price=transit_price,
                                             total_count=total_count,
                                             transit_price=transit_price)

            # todo:用户订单中有几个商品　需要向df_order_goods表中加入几条数据
            # 给df_order_goods加记录　order sku count price comment
            conn = get_redis_connection('default')
            cart_key = 'cart_%d' % user.id
            sku_ids = sku_ids.split(',') # 将字符串变为字符串列表
            for sku_id in sku_ids:
                for i in range(3):
                    # 根据商品id sku_id 获取商品的信息
                    try:
                        sku = GoodsSKU.objects.get(id=sku_id)
                    except GoodsSKU.DoesNotExist:
                        # 商品不存在
                        # 进行事务回滚 也就不会创建订单信息表
                        transaction.savepoint_rollback(save_id)
                        return JsonResponse({'res': 4, "errmsg": '商品不存在'})

                    # 从redis中获取用户购买商品的数量
                    count = int(conn.hget(cart_key,sku_id))

                    # todo:判断商品的库存
                    # 防止同一时间 其他用户购买商品 导致库存不足
                    if count > sku.stock:
                        # 进行事务回滚 不创建订单信息表
                        transaction.savepoint_rollback(save_id)
                        return JsonResponse({'res': 6, "errmsg": '商品库存不足'})

                    # 更新商品的库存和销量
                    orgin_stock = sku.stock
                    new_stock = orgin_stock - count
                    new_sales = sku.sales + count

                    print('user_id:%d,times:%d,sku.stock:%d'%(user.id,i,sku.stock))
                    # time.sleep(10)

                    # update df_goods_sku set stock=new_stock.sales=new_sales
                    # where id=sku_id and stock = orgin_stock
                    # res返回受影响的行数 要么是1要么是0
                    # 判断库存是否跟原来一致
                    res = GoodsSKU.objects.filter(id=sku_id,stock=orgin_stock).update(stock=new_stock,
                                                                                sales=new_sales)
                    if res == 0:# 库存被修改过 返回错误信息
                        if i == 2:
                            # 尝试的第三次 还失败 返回失败
                            transaction.savepoint_rollback(save_id)
                            return JsonResponse({'res': 7, "errmsg": '下单失败2'})
                        continue # 跳过本次循环 执行下一次循环

                    # todo:向df_order_goods添加一条记录  每一个商品都要添加订单商品
                    OrderGoods.objects.create(order=order,
                                              sku=sku,
                                              count=count,
                                              price=sku.price)

                    # todo:累加计算订单商品的总数目和总价格
                    # 小计
                    amount = sku.price * count
                    total_count += count
                    total_price += amount

                    # 跳出循环
                    break

            # todo:更新订单信息表中的总数量和总价格
            order.total_count = total_count
            order.total_price = total_price
            order.save()
        except Exception as e:
            # 捕获异常 并进行回滚
            print(e)
            transaction.savepoint_rollback(save_id)
            return JsonResponse({'res': 7, "errmsg": '下单失败'})

        # 没有问题 提交事务到数据库
        transaction.savepoint_commit(save_id)

        # todo:用户提交订单后 清除用户购物车中的记录
        # 从redis中删除商品列表 hdel(name,*keys)
        conn.hdel(cart_key,*sku_ids)

        return JsonResponse({'res': 5, "message": '创建订单成功'})

# 订单支付
# ajax post
# 前端传递参数:order_id订单的id
# /order/pay
class OrderPayView(View):
    '''订单支付'''
    def post(self,request):
        # 用户是否登录
        print('post请求进来了')
        user = request.user
        if not user.is_authenticated():
            return JsonResponse({'res':0,"errmsg":"用户未登录"})

        # 接收参数　订单的id
        order_id = request.POST.get('order_id')

        # 校验参数
        if not order_id:
            return JsonResponse({'res':1,"errmsg":"无效的订单id"})

        try:
            # 判断订单id　是否是这个用户的订单　支付方式是否是支付宝　订单状态是否是未支付的状态
            order = OrderInfo.objects.get(order_id=order_id,
                                          user=user,
                                          pay_method=3,
                                          order_status=1)
        except OrderInfo.DoesNotExist:
            # 订单不存在
            return JsonResponse({'res':2,"errmsg":"订单错误"})

        # 业务处理:使用python 的sdk调用支付宝的支付接口
        # 1.初始化
        alipay = AliPay(
            appid="2016092500591558", # 沙箱的APPID
            app_notify_url=None,  # 默认回调url None表示不传# app_private_key_string=app_private_key_string,
            app_private_key_path=os.path.join(settings.BASE_DIR,'apps/order/app_private_key.pem'),
            # 支付宝的公钥，验证支付宝回传消息使用，不是你自己的公钥,
            # alipay_public_key_string=alipay_public_key_string,
            alipay_public_key_path=os.path.join(settings.BASE_DIR,'apps/order/alipay_public_key.pem'),
            sign_type="RSA2",  # RSA 或者 RSA2
            debug=True  # 默认False True表示使用沙箱的地址,否则访问的是真是环境的地址
        )

        # 2.调用支付接口
        # 电脑网站支付 需要跳转到https://openapi.alipaydev.com/gateway.do? + order_string
        total_pay = order.total_price+order.transit_price # Decimal类型不能直接转化为json 需要先转化为字符串
        order_string = alipay.api_alipay_trade_page_pay(
            out_trade_no=order_id, # 订单的id
            total_amount=str(total_pay), # 支付总金额
            subject='天天生鲜%s' % order_id,
            return_url=None,
            notify_url=None  # 可选, 不填则使用默认notify url
        )

        # 返回应答
        pay_url = 'https://openapi.alipaydev.com/gateway.do?' + order_string
        return JsonResponse({'res':3,'pay_url':pay_url})


# 订单支付结果查询
# ajax post
# 前端传递参数:order_id订单的id
# /order/check
class OrderCheckView(View):
    '''查看订单支付结果'''
    def post(self,request):
        # 判断用户是否登录
        user = request.user
        if not user.is_authenticated():
            return JsonResponse({"res":0,"errmsg":"请先登录!"})

        # 校验参数
        order_id = request.POST.get('order_id')
        if not order_id:
            return JsonResponse({"res":1,"errmsg":"无效的订单号"})

        # 判断订单号是否存在
        try:
            # 判断订单id　是否是这个用户的订单　支付方式是否是支付宝　订单状态是否是未支付的状态
            order = OrderInfo.objects.get(order_id=order_id,
                                             order_status=1,
                                             user=user,
                                             pay_method=3)
        except OrderInfo.DoesNotExist:
            return JsonResponse({"res":2,"errmsg":"订单不存在"})

        # 业务处理:使用python 的sdk调用支付宝的支付接口
        # 1.初始化
        alipay = AliPay(
            appid="2016092500591558",  # 沙箱的APPID
            app_notify_url=None,  # 默认回调url None表示不传# app_private_key_string=app_private_key_string,
            app_private_key_path=os.path.join(settings.BASE_DIR, 'apps/order/app_private_key.pem'),
            # 支付宝的公钥，验证支付宝回传消息使用，不是你自己的公钥,
            # alipay_public_key_string=alipay_public_key_string,
            alipay_public_key_path=os.path.join(settings.BASE_DIR, 'apps/order/alipay_public_key.pem'),
            sign_type="RSA2",  # RSA 或者 RSA2
            debug=True  # 默认False True表示使用沙箱的地址,否则访问的是真是环境的地址
        )

        while True:
            # 调用支付宝的交易查询接口
            # 返回结果response为字典
            response = alipay.api_alipay_trade_query(order_id)

            # response = {
            #         "trade_no": "2017032121001004070200176844",    # 支付宝的交易号
            #         "code": "10000",　                             # 接口调用是否成功
            #         "invoice_amount": "20.00",
            #         "open_id": "20880072506750308812798160715407",
            #         "fund_bill_list": [
            #             {
            #                 "amount": "20.00",
            #                 "fund_channel": "ALIPAYACCOUNT"
            #             }
            #         ],
            #         "buyer_logon_id": "csq***@sandbox.com",
            #         "send_pay_date": "2017-03-21 13:29:17",
            #         "receipt_amount": "20.00",
            #         "out_trade_no": "out_trade_no15",
            #         "buyer_pay_amount": "20.00",
            #         "buyer_user_id": "2088102169481075",
            #         "msg": "Success",
            #         "point_amount": "0.00",
            #         "trade_status": "TRADE_SUCCESS",                # 支付结果
            #         "total_amount": "20.00"
            #     }

            code = response.get('code')
            trade_status = response.get('trade_status')
            # 接口调用成功和支付成功
            if code == '10000' and trade_status == 'TRADE_SUCCESS':
                # 交易成功
                # 获取支付宝的交易号　也就是订单号
                trade_no = response.get('trade_no')
                # 更新订单状态
                order.trade_no = trade_no
                order.order_status = 4 # 待评价
                order.save()

                # 返回结果
                return JsonResponse({"res":3,"message":"支付成功"})


            # 接口调用成功正在等待买家支付
            elif code == '40004' or (code == '10000' and trade_status == 'WAIT_BUYER_PAY'):
                # 等买家付款
                # code为40004　业务处理失败　可能一会就会成功
                time.sleep(5)
                continue # 跳过本次循环　不执行下面的程序　从头开始再来一遍

            else:
                # 支付出错
                print(code)
                return JsonResponse({"res":4,"errmsg":"支付失败"})


# 订单评价
# post  get
# 前端传来的参数: order_id
# /order/comment
class OrderCommentView(LoginRequiredMixin,View):
    '''订单评论'''
    def get(self,request,order_id):
        '''提供评论页面'''
        user = request.user

        # 校验数据
        if not order_id:
            # 如果没有传来订单号 返回到用户订单页面
            return redirect(reverse('user:order'))

        try:
            order = OrderInfo.objects.get(order_id=order_id,user=user)
        except OrderInfo.DoesNotExist:
            # 订单不存在
            return redirect(reverse('user:order'))

        # 根据订单的状态获取订单的状态标题
        order.status_name = OrderInfo.ORDER_STATUS[order.order_status]

        # 获取订单商品信息
        order_skus = OrderGoods.objects.filter(order_id=order_id)
        for order_sku in order_skus:
            # 计算商品的小计
            price = order_sku.price
            count = order_sku.count
            amount = price * count
            # 动态给order_sku增加属性amount 保存商品的小计
            order_sku.amount = amount
        # 动态给order增加属性order_skus 保存订单商品信息
        order.order_skus = order_skus

        # 使用模板
        return render(request,'order_comment.html',locals())

    def post(self,request,order_id):
        '''处理评论内容'''
        # 校验数据
        if not order_id:
            return render(reverse('user:order'))

        try:
            order = OrderInfo.objects.get(order_id=order_id)
        except OrderInfo.DoesNotExist:
            return render(reverse('user:order'))

        # 获取评论条数
        total_count = request.POST.get('total_count')
        total_count = int(total_count)

        # 循环获取订单中商品的评论内容
        for i in range(1,total_count+1):
            # 获取评论的商品的id
            sku_id = request.POST.get('sku_%d'%i) # sku_1 sku_2
            # 获取评论的商品的内容
            content = request.POST.get('content_%d'%i,'用户未评价')
            try:
                order_goods = OrderGoods.objects.get(order=order,sku_id=sku_id)
            except OrderGoods.DoesNotExist:
                # 出错不管他 下一个
                continue

            order_goods.comment = content
            order_goods.save()

        order.order_status = 5 # 已完成
        order.save()

        return redirect(reverse('user:order',kwargs={'page':1}))













