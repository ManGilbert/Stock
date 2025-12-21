from django.urls import path
from . import views

urlpatterns = [
    # ---------- AUTH ----------
    path('', views.index, name="index"),
    path('stock/user/account/login/', views.login_view, name="login_view"),
    path('stock/user/account/logout/', views.logout_view, name="logout_view"),


    # ---------- Product URLs----------
    path('stock/user/account/product/', views.products_view, name="products_view"),
    path('stock/user/account/products/', views.products_view, name='products'),  # main product page

    # --- Stock Movement URLs ---
    path('stock/user/account/movements/', views.stock_movement_view, name='stock_movement_view'),
    path('stock/user/account/movements/all/records/', views.stock_movement_all_records_view, name='stock_movement_all_records_view'),

    # --- Stock URLs ---
    path('stock/user/account/stocks', views.stock_view, name='stock_view'),

    # --- Stock URLs ---
    path('stock/user/account/report', views.report_view, name='report_view'),

    # --- Users Profile URLs ---
    path('stock/user/account/profile/', views.profile_view, name='profile_view'),
    path('stock/user/account/reset/auth', views.change_auth_view, name='change_auth_view'),
    
    # --- create Users URLs ---
    path("stock/admin/create/account/", views.create_user_account, name="create_user_account"),
    path("stock/create/branch/", views.create_branch_with_manager, name="create_branch_with_manager"),
    path('stock/manager/create/staff/', views.create_staff_with_manager, name='create_staff_with_manager'),

     # --- settings URLs ---
    path("stock/settings/", views.settings_view, name="settings_view"),

    # --- reset password URLs ---
    path("forgot-password/", views.forgot_password_otp, name="forgot-password-otp"),
    path("verify-otp/", views.verify_otp, name="verify-otp"),
    path("resend-otp/", views.resend_otp, name="resend-otp"),

] 
