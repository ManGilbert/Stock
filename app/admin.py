from django.contrib import admin
from .models import (
    AdminInfo, Account, UserInfo, Branch,
    Product, Stock, StockMovement, StockMovementLog
)

# -------------------- 1. AdminInfo --------------------
@admin.register(AdminInfo)
class AdminInfoAdmin(admin.ModelAdmin):
    list_display = ("firstname", "lastname", "email", "created_at")
    search_fields = ("firstname", "lastname", "email")
    readonly_fields = ("created_at",)


# -------------------- 2. Account --------------------
@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "created_at")
    search_fields = ("name", "phone")
    readonly_fields = ("created_at",)


# -------------------- 3. Users --------------------
@admin.register(UserInfo)
class UserInfoAdmin(admin.ModelAdmin):
    list_display = ("firstname", "lastname", "email", "account", "role", "is_active", "created_at")
    list_filter = ("role", "is_active", "account")
    search_fields = ("firstname", "lastname", "email")
    readonly_fields = ("created_at",)


# -------------------- 4. Branch --------------------
@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ("branch_name", "account", "manager", "created_at")
    list_filter = ("account",)
    search_fields = ("branch_name",)
    readonly_fields = ("created_at",)


# -------------------- 5. Product --------------------
@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "branch", "account", "cost_price", "selling_price", "created_at")
    list_filter = ("category", "account", "branch")
    search_fields = ("name",)
    readonly_fields = ("created_at",)


# -------------------- 6. Stock --------------------
@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = ("product", "branch", "quantity", "last_updated")
    list_filter = ("branch", "product")
    search_fields = ("product__name",)
    readonly_fields = ("last_updated",)


# -------------------- 7. StockMovement --------------------
class StockMovementLogInline(admin.TabularInline):
    model = StockMovementLog
    extra = 0
    readonly_fields = ("before_qty", "after_qty", "profit", "payment_method", "changed_at", "changed_by")


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = (
        "product", "branch", "movement_type", "quantity",
        "selling_amount", "profit", "payment_method", "created_by", "created_at"
    )
    list_filter = ("movement_type", "branch", "product", "payment_method")
    search_fields = ("product__name",)
    readonly_fields = ("created_at", "profit")
    inlines = [StockMovementLogInline]


# -------------------- 8. StockMovementLog --------------------
@admin.register(StockMovementLog)
class StockMovementLogAdmin(admin.ModelAdmin):
    list_display = ("movement", "before_qty", "after_qty", "profit", "payment_method", "changed_by", "changed_at")
    list_filter = ("changed_by", "payment_method")
    readonly_fields = ("before_qty", "after_qty", "profit", "payment_method", "changed_at")
