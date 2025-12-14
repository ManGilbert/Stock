from django.urls import path
from . import views

urlpatterns = [
    # ---------- AUTH ----------
    path('', views.index, name="index"),
    path('stock-login/', views.login_view, name="login_view"),
    path('stock-logout/', views.logout_view, name="logout_view"),


    # ---------- PRODUCT CRUD ----------
    path('stock-product/', views.products_view, name="products_view"),
    path('products/', views.products_view, name='products'),  # main product page


        # ---------- PRODUCT CRUD ----------
    ##path('stock-movement/', views.stock_movement_view, name="stock_movement_view"),
    ##path('smovement/', views.smovement_view, name='smovement'),  # main product page

        # --- Stock Movement URLs ---
    path('stock-movements/', views.stock_movement_view, name='stock_movement_view'),

    # Optional: other CRUD pages like accounts, branches, users
    # path('accounts/', views.accounts_view, name='accounts'),
    # path('branches/', views.branches_view, name='branches'),

            # --- Stock URLs ---
    path('stock/stocks', views.stock_view, name='stock_view'),


] 
