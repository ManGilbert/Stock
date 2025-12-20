from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.contrib.auth.hashers import make_password, check_password

# -------------------- 1. Admin --------------------
class AdminInfo(models.Model):
    firstname = models.CharField(max_length=50)
    lastname = models.CharField(max_length=50)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.password and not self.password.startswith("pbkdf2_"):
            self.password = make_password(self.password)
        super().save(*args, **kwargs)

    def set_password(self, raw_password):
        self.password = make_password(raw_password)
        self.save()

    def check_password(self, raw_password):
        return check_password(raw_password, self.password)

    def __str__(self):
        return f"{self.firstname} {self.lastname}"


# -------------------- 2. Account --------------------
class Account(models.Model):
    name = models.CharField(max_length=100)
    address = models.TextField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)

    is_active = models.BooleanField(default=True)  # ✅ ADD THIS

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    def delete(self, *args, **kwargs):
        if self.users.exists() or self.branches.exists() or self.products.exists() or \
           StockMovement.objects.filter(product__account=self).exists():
            raise ValidationError("Cannot delete Account with users, branches, products, or stock movements.")
        super().delete(*args, **kwargs)


# -------------------- 3. Users --------------------
class UserInfo(models.Model):
    ROLE_CHOICES = (
        ('manager', 'Manager'),
        ('staff', 'Staff'),
    )

    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='users')
    firstname = models.CharField(max_length=50)
    lastname = models.CharField(max_length=50)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=255)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    is_active = models.BooleanField(default=True)
    branch = models.ForeignKey(
        'Branch',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='staff'  # staff in this branch
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.password and not self.password.startswith("pbkdf2_"):
            self.password = make_password(self.password)
        super().save(*args, **kwargs)

    def set_password(self, raw_password):
        self.password = make_password(raw_password)
        self.save()

    def check_password(self, raw_password):
        return check_password(raw_password, self.password)

    def delete(self, *args, **kwargs):
        if StockMovement.objects.filter(created_by=self).exists():
            raise ValidationError("Cannot delete user with stock movement records.")
        super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.firstname} {self.lastname} ({self.role})"


# -------------------- 4. Branch --------------------
class Branch(models.Model):
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='branches')
    branch_name = models.CharField(max_length=100)
    manager = models.ForeignKey(
        UserInfo,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='managed_branch'  # branch that this user manages
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.branch_name} - {self.account.name}"

    def delete(self, *args, **kwargs):
        if self.products.exists() or self.stocks.exists() or StockMovement.objects.filter(branch=self).exists():
            raise ValidationError("Cannot delete Branch with products, stocks, or stock movements.")
        super().delete(*args, **kwargs)


# -------------------- 5. Product --------------------
class Product(models.Model):
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='products')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='products')
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=50)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.branch.branch_name})"

    def delete(self, *args, **kwargs):
        if self.stocks.exists() or self.movements.exists():
            raise ValidationError("Cannot delete Product with stock or stock movement records.")
        super().delete(*args, **kwargs)


# -------------------- 6. Stock --------------------
class Stock(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='stocks')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='stocks')
    quantity = models.IntegerField(default=0)
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.product.name} - {self.quantity}"

    def delete(self, *args, **kwargs):
        if self.quantity > 0:
            raise ValidationError("Cannot delete Stock with quantity greater than 0.")
        super().delete(*args, **kwargs)


# -------------------- 7. Stock Movements --------------------
class StockMovement(models.Model):
    MOVEMENT_CHOICES = (
        ('IN', 'IN'),
        ('OUT', 'OUT'),
    )

    PAYMENT_CHOICES = (
        ('cash', 'Cash'),
        ('momo', 'Mobile Money'),
    )

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='movements')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='movements')
    movement_type = models.CharField(max_length=10, choices=MOVEMENT_CHOICES)
    quantity = models.IntegerField()
    selling_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    profit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    payment_method = models.CharField(max_length=10, choices=PAYMENT_CHOICES, null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(UserInfo, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.movement_type == 'OUT':
            stock = Stock.objects.filter(product=self.product, branch=self.branch).first()
            if not stock or self.quantity > stock.quantity:
                raise ValidationError(
                    f"Cannot sell {self.quantity} units. Only {stock.quantity if stock else 0} available."
                )
            if not self.payment_method:
                raise ValidationError("Payment method is required for OUT movements.")

    def save(self, *args, **kwargs):
        self.clean()
        if self.movement_type == 'OUT':
            cost_total = float(self.product.cost_price) * self.quantity
            selling_total = float(self.selling_amount or 0)
            self.profit = selling_total - cost_total
        else:
            self.profit = 0

        with transaction.atomic():
            stock, created = Stock.objects.get_or_create(
                product=self.product,
                branch=self.branch,
                defaults={'quantity': 0}
            )

            if self.pk:
                old = StockMovement.objects.get(pk=self.pk)
                if old.movement_type == 'IN':
                    stock.quantity -= old.quantity
                elif old.movement_type == 'OUT':
                    stock.quantity += old.quantity

            before_qty = stock.quantity

            if self.movement_type == 'IN':
                stock.quantity += self.quantity
            elif self.movement_type == 'OUT':
                stock.quantity -= self.quantity

            stock.save()
            super().save(*args, **kwargs)

            StockMovementLog.objects.create(
                movement=self,
                before_qty=before_qty,
                after_qty=stock.quantity,
                changed_by=self.created_by,
                profit=self.profit,
                payment_method=self.payment_method
            )

    def delete(self, *args, **kwargs):
        with transaction.atomic():
            stock = Stock.objects.get(product=self.product, branch=self.branch)

            if self.movement_type == 'IN' and stock.quantity < self.quantity:
                raise ValidationError(
                    f"Cannot delete this movement. Stock would become negative."
                )

            if self.movement_type == 'IN':
                stock.quantity -= self.quantity
            elif self.movement_type == 'OUT':
                stock.quantity += self.quantity

            before_qty = stock.quantity + self.quantity if self.movement_type == "IN" else stock.quantity - self.quantity
            after_qty = stock.quantity

            stock.save()
            StockMovementLog.objects.create(
                movement=self,
                before_qty=before_qty,
                after_qty=after_qty,
                changed_by=self.created_by,
                profit=(self.profit * -1),
                payment_method=self.payment_method
            )
            super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.movement_type} {self.quantity} of {self.product.name} at {self.branch.branch_name}"


# -------------------- 8. Stock Movement Log --------------------
class StockMovementLog(models.Model):
    movement = models.ForeignKey(StockMovement, on_delete=models.CASCADE, related_name='logs')
    before_qty = models.IntegerField()
    after_qty = models.IntegerField()
    profit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    payment_method = models.CharField(max_length=10, null=True, blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)
    changed_by = models.ForeignKey(UserInfo, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"Log: {self.movement.product.name} ({self.before_qty} -> {self.after_qty}) profit={self.profit}"
