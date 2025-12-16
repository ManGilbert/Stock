from django.urls import path
from . import views

urlpatterns = [
    # ---------- AUTH ----------
    path('', views.index, name="index"),
    path('stock/login/', views.login_view, name="login_view"),
    path('stock/logout/', views.logout_view, name="logout_view"),


    # ---------- Product URLs----------
    path('stock/product/', views.products_view, name="products_view"),
    path('products/', views.products_view, name='products'),  # main product page

    # --- Stock Movement URLs ---
    path('stock/movements/', views.stock_movement_view, name='stock_movement_view'),
    path('stock/movements/all/records/', views.stock_movement_all_records_view, name='stock_movement_all_records_view'),

    # --- Stock URLs ---
    path('stock/stocks', views.stock_view, name='stock_view'),

    # --- Stock URLs ---
    path('stock/report', views.report_view, name='report_view'),

    # --- Users Profile URLs ---
    path('stock/profile/', views.profile_view, name='profile_view'),
    path('stock/reset/auth', views.change_auth_view, name='change_auth_view'),
    
    
] 
