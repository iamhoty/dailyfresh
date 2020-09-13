from django.conf.urls import url
from order.views import *
urlpatterns = [
    url(r"^place/$",OrderPlaceView.as_view(),name='place'),# 提交订单页面显示
    url(r'^commit/$',OrderCommitView.as_view(),name='commit'),# 订单创建
    url(r'^pay/$',OrderPayView.as_view(),name='pay'),# 订单支付
    url(r'^check/$',OrderCheckView.as_view(),name='check'),# 查看订单支付结果
    url(r'^comment/(?P<order_id>.+)/$',OrderCommentView.as_view(),name='comment'),# 订单评论
]
