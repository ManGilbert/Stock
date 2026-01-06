# Django shortcuts & utilities
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse

# Django auth & security
from django.contrib.auth.hashers import make_password, check_password

# Django DB
from django.db import transaction
from django.db.models import (
    Sum, F, Case, When, Value, IntegerField,
    ExpressionWrapper, DecimalField, Count, Q
)

# Django time & utils
from django.utils import timezone
from django.utils.timezone import now
from datetime import timedelta

# Email
from django.core.mail import send_mail
from django.conf import settings

# Models
from .models import (
    AdminInfo,
    UserInfo,
    Account,
    Branch,
    Product,
    Stock,
    StockMovement,
    PasswordResetOTP,
)

# Python stdlib
import re



def index(request):
    context = {}

    # Admin dashboard
    if request.session.get('admin_id'):
        admin = AdminInfo.objects.only('id', 'firstname', 'lastname').get(id=request.session['admin_id'])

        context.update({
            'role': 'admin',
            'user': admin,  # So template can do {{ user.firstname }} etc.

            'total_accounts': Account.objects.count(),
            'total_users': UserInfo.objects.count(),
            'total_branches': Branch.objects.count(),
            'total_products': Product.objects.count(),

            'total_stock': Stock.objects.aggregate(total=Sum('quantity'))['total'] or 0,
            'total_profit': StockMovement.objects.aggregate(total=Sum('profit'))['total'] or 0,
        })

        return render(request, 'index.html', context)

    # Manager or Staff dashboard
    if request.session.get('user_id'):
        user = UserInfo.objects.select_related('account').get(id=request.session['user_id'])

        # Manager dashboard
        if user.role == 'manager':
            branches = Branch.objects.filter(account=user.account)

            context.update({
                'role': 'manager',
                'user': user,

                'total_branches': branches.count(),
                'total_staff': UserInfo.objects.filter(account=user.account, role='staff').count(),
                'total_products': Product.objects.filter(account=user.account).count(),

                'total_stock': Stock.objects.filter(branch__in=branches).aggregate(total=Sum('quantity'))['total'] or 0,
                'total_profit': StockMovement.objects.filter(branch__in=branches).aggregate(total=Sum('profit'))['total'] or 0,
            })

        # Staff dashboard
        else:
            # Detect staff branch - the first branch for their account with stock
            staff_branch = Branch.objects.filter(account=user.account).filter(products__stocks__isnull=False).distinct().first()

            context.update({
                'role': 'staff',
                'user': user,

                'branch_name': staff_branch.branch_name if staff_branch else "N/A",
                'total_products': Product.objects.filter(branch=staff_branch).count() if staff_branch else 0,
                'total_stock': Stock.objects.filter(branch=staff_branch).aggregate(total=Sum('quantity'))['total'] or 0 if staff_branch else 0,
                'total_profit': StockMovement.objects.filter(branch=staff_branch).aggregate(total=Sum('profit'))['total'] or 0 if staff_branch else 0,
            })

        return render(request, 'index.html', context)

    # If no user found, redirect to login
    return redirect('login_view')

class SessionExpiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        # If user was logged in but role/session is missing -> session expired
        if request.session.get("was_logged_in") and not request.session.get("role"):

            # Clear session
            request.session.flush()

            # Redirect to login with GET param
            return redirect('/login_view/?session_expired=1')

        response = self.get_response(request)

        # Mark user as logged in if role exists
        if request.session.get("role"):
            request.session["was_logged_in"] = True

        return response

# ---------- login section ----------
def login_view(request):

    # Show session expired message if redirected
    if request.GET.get("session_expired"):
        messages.error(request, "Your session expired. Please login again.")

    # GET request → show login page
    if request.method != "POST":
        return render(request, "auth-login.html")

    user_type = request.POST.get("user_type")
    email = request.POST.get("email", "").strip()
    password = request.POST.get("password", "")

    # Validation
    if not user_type:
        messages.error(request, "Please select user type.")
        return render(request, "auth-login.html")

    if not email or not password:
        messages.error(request, "Please enter email & password.")
        return render(request, "auth-login.html")

    # ------------------- ADMIN LOGIN -------------------
    if user_type == "admin":
        user = _authenticate_admin(email, password)
        if not user:
            messages.error(request, "Invalid admin email or password.")
            return render(request, "auth-login.html")

        request.session["admin_id"] = user.id
        request.session["role"] = "admin"
        request.session["user_name"] = user.firstname
        request.session.set_expiry(1800)

        messages.success(request, "Logged in successfully!")
        return redirect("index")

    # ------------------- USER LOGIN ---------------------
    elif user_type == "user":
        user = _authenticate_user(email, password)
        if not user:
            messages.error(request, "Invalid user email or password.")
            return render(request, "auth-login.html")

        # ---------- BLOCK DISABLED ACCOUNT ----------
        if not user.account or not user.account.is_active:
            messages.error(
                request,
                "Ifata buguzi ryawe ryarangiye. Please contact the administrator." #Your subscription has expired
            )
            return render(request, "auth-login.html")

        # ---------- BLOCK DISABLED USER ----------
        if not user.is_active:
            messages.error(request, "Access denied tolk to you boss")
            return render(request, "auth-login.html")

        # ---------- DETERMINE BRANCH INFO ----------
        branch_name = None
        branch_id = None

        if user.role == "manager":
            branch = Branch.objects.filter(manager=user).first()
            if branch:
                branch_name = branch.branch_name
                branch_id = branch.id

        elif user.role == "staff":
            if user.branch:
                branch_name = user.branch.branch_name
                branch_id = user.branch.id

        # ---------- SESSION ----------
        request.session["user_id"] = user.id
        request.session["role"] = user.role
        request.session["account_id"] = user.account.id
        request.session["user_name"] = user.firstname
        request.session["branch_name"] = branch_name
        request.session["branch_id"] = branch_id
        request.session.set_expiry(1800)

        messages.success(request, "Logged in successfully!")
        return redirect("index")

    # Fallback
    messages.error(request, "Invalid request.")
    return render(request, "auth-login.html")


# -----------------------
# AUTHENTICATION HELPERS
# -----------------------
def _authenticate_admin(email, password):
    try:
        admin = AdminInfo.objects.get(email=email)
    except AdminInfo.DoesNotExist:
        return None

    if check_password(password, admin.password):
        return admin
    return None

def _authenticate_user(email, password):
    try:
        user = UserInfo.objects.get(email=email)
    except UserInfo.DoesNotExist:
        return None

    if check_password(password, user.password):
        return user
    return None


# ---------- user profile section ----------
def profile_view(request):

    admin_id = request.session.get('admin_id')
    user_id = request.session.get('user_id')

    # ---------- ADMIN ----------
    if admin_id:
        admin = AdminInfo.objects.get(id=admin_id)

        if request.method == 'POST':
            admin.firstname = request.POST.get('firstname')
            admin.lastname = request.POST.get('lastname')
            admin.email = request.POST.get('email')
            admin.save()

            messages.success(request, 'Profile updated successfully')
            return redirect('profile_view')

        return render(request, 'profile.html', {
            'person': admin,
            'role': 'Admin',
            'branch': None
        })

    # ---------- USER ----------
    elif user_id:
        user = UserInfo.objects.select_related('account').get(id=user_id)

        if request.method == 'POST':
            user.firstname = request.POST.get('firstname')
            user.lastname = request.POST.get('lastname')
            user.email = request.POST.get('email')
            user.save()

            messages.success(request, 'Profile updated successfully')
            return redirect('profile_view')

        return render(request, 'profile.html', {
            'person': user,
            'role': user.role.title(),
            'branch': user.branch.branch_name if hasattr(user, 'branch') and user.branch else None
        })

    # ---------- NOT LOGGED IN ----------
    return redirect('login_view')


# ---------- User change password ----------
def change_auth_view(request):

    admin_id = request.session.get('admin_id')
    user_id = request.session.get('user_id')

    # -------- IDENTIFY USER --------
    if admin_id:
        person = AdminInfo.objects.get(id=admin_id)
        user_type = "admin"

    elif user_id:
        person = UserInfo.objects.get(id=user_id)
        user_type = "user"

    else:
        return redirect('login_view')

    # -------- HANDLE POST --------
    if request.method == "POST":

        action = request.POST.get("action")

        # CHANGE PASSWORD
        if action == "change_password":

            current_password = request.POST.get("current_password")
            new_password = request.POST.get("password")
            confirm_password = request.POST.get("confirm_password")

            if not check_password(current_password, person.password):
                messages.error(request, "Current password is incorrect.")
                return redirect("change_auth_view")

            if new_password != confirm_password:
                messages.error(request, "New passwords do not match.")
                return redirect("change_auth_view")

            if len(new_password) < 6:
                messages.error(request, "Password must be at least 6 characters.")
                return redirect("change_auth_view")

            person.password = make_password(new_password)
            person.save()

            messages.success(request, "Password changed successfully.")
            return redirect("change_auth_view")

        # UPDATE EMAIL (2FA BLOCK)
        elif action == "update_email":

            email = request.POST.get("email")

            if not email:
                messages.error(request, "Email cannot be empty.")
                return redirect("change_auth_view")

            person.email = email
            person.save()

            messages.success(request, "Email updated successfully.")
            return redirect("change_auth_view")

    return render(request, "reset-auth.html", {
        "person": person,
        "user_type": user_type
    })

# --------- logout section ----------
def logout_view(request):
    request.session.flush()
    return redirect('login_view')

# ---------- product section ----------
def products_view(request):
    # -------------------- LOGIN CHECK --------------------
    if not request.session.get('user_id') and not request.session.get('admin_id'):
        return redirect('login_view')

    role = request.session.get('role')
    user = None

    if role != "admin":
        user = get_object_or_404(UserInfo, id=request.session["user_id"])

    # -------------------- BASE QUERY --------------------
    if role == "admin":
        products = Product.objects.all()

    elif role == "manager":
        products = Product.objects.filter(account=user.account)

    else:  # staff → ONLY assigned branch
        if not user.branch:
            products = Product.objects.none()
        else:
            products = Product.objects.filter(branch=user.branch)

    # -------------------- HANDLE POST --------------------
    if request.method == "POST":
        action = request.POST.get("action")

        # ---------- ADD PRODUCT ----------
        if action == "add":
            name = request.POST.get("name")
            branch_id = request.POST.get("branch")
            category = request.POST.get("category")
            cost_price = request.POST.get("cost_price")
            selling_price = request.POST.get("selling_price")

            if not branch_id:
                messages.error(request, "Please select a branch.")
                return redirect("products")

            # STAFF BRANCH LOCK
            if role == "staff":
                if not user.branch or int(branch_id) != user.branch.id:
                    messages.error(
                        request,
                        "You can only add products to your assigned branch."
                    )
                    return redirect("products")

            try:
                # Branch scope
                if role == "admin":
                    branch = Branch.objects.get(id=branch_id)
                else:
                    branch = Branch.objects.get(
                        id=branch_id,
                        account=user.account
                    )

                # Duplicate check per branch
                if Product.objects.filter(
                    branch=branch,
                    name__iexact=name
                ).exists():
                    messages.error(
                        request,
                        f"Product '{name}' already exists in this branch."
                    )
                    return redirect("products")

                Product.objects.create(
                    account=branch.account,
                    branch=branch,
                    name=name,
                    category=category,
                    cost_price=cost_price,
                    selling_price=selling_price
                )

                messages.success(
                    request,
                    f"Product '{name}' added successfully."
                )

            except Branch.DoesNotExist:
                messages.error(request, "Invalid branch selected.")

        # ---------- UPDATE PRODUCT ----------
        elif action == "update":
            product_id = request.POST.get("product_id")

            if not product_id or not product_id.isdigit():
                messages.error(request, "Invalid product ID.")
                return redirect("products")

            # Product scope
            if role == "admin":
                product = get_object_or_404(Product, id=int(product_id))
            elif role == "manager":
                product = get_object_or_404(
                    Product,
                    id=int(product_id),
                    account=user.account
                )
            else:  # staff
                product = get_object_or_404(
                    Product,
                    id=int(product_id),
                    branch=user.branch
                )

            branch_id = request.POST.get("branch")

            # STAFF BRANCH LOCK
            if role == "staff" and int(branch_id) != user.branch.id:
                messages.error(
                    request,
                    "You cannot move a product to another branch."
                )
                return redirect("products")

            try:
                if role == "admin":
                    branch = Branch.objects.get(id=branch_id)
                else:
                    branch = Branch.objects.get(
                        id=branch_id,
                        account=user.account
                    )

                # Duplicate name in target branch
                if Product.objects.filter(
                    branch=branch,
                    name__iexact=request.POST.get("name")
                ).exclude(id=product.id).exists():
                    messages.error(
                        request,
                        "This product already exists in the selected branch."
                    )
                    return redirect("products")

                product.branch = branch
                product.name = request.POST.get("name")
                product.category = request.POST.get("category")
                product.cost_price = request.POST.get("cost_price")
                product.selling_price = request.POST.get("selling_price")
                product.save()

                messages.success(
                    request,
                    f"Product '{product.name}' updated successfully."
                )

            except Branch.DoesNotExist:
                messages.error(request, "Invalid branch selected.")

        # ---------- DELETE PRODUCT ----------
        elif action == "delete":
            product_id = request.POST.get("product_id")

            if not product_id or not product_id.isdigit():
                messages.error(request, "Invalid product ID.")
                return redirect("products")

            # Product scope
            if role == "admin":
                product = get_object_or_404(Product, id=int(product_id))
            elif role == "manager":
                product = get_object_or_404(
                    Product,
                    id=int(product_id),
                    account=user.account
                )
            else:  # staff
                product = get_object_or_404(
                    Product,
                    id=int(product_id),
                    branch=user.branch
                )

            product_name = product.name
            product.delete()

            messages.success(
                request,
                f"Product '{product_name}' deleted successfully."
            )

        else:
            messages.error(request, "Invalid action.")

        return redirect("products")

    # -------------------- FINAL QUERY --------------------
    products = products.select_related('branch').order_by("-id")

    return render(request, 'product_list.html', {
        'products': products,
        'role': role,
        'user': user
    })


# --- stock movement view section ---
try:
    from zoneinfo import ZoneInfo
    KIGALI_TZ = ZoneInfo("Africa/Kigali")
except ImportError:
    import pytz
    KIGALI_TZ = pytz.timezone("Africa/Kigali")

    # -------------------- stock movement view Section--------------------
def stock_movement_view(request):
    # -------------------- LOGIN CHECK --------------------
    if not request.session.get('user_id') and not request.session.get('admin_id'):
        return redirect('login_view')

    role = request.session.get('role')
    user = None

    if role != "admin":
        user = get_object_or_404(UserInfo, id=request.session["user_id"])

    # -------------------- HANDLE POST --------------------
    if request.method == "POST":
        action = request.POST.get("action")
        movement_id = request.POST.get("movement_id")

        # ---------- ADD / UPDATE ----------
        if action in ["add", "update"]:
            product_id = request.POST.get("product")
            branch_id = request.POST.get("branch")
            movement_type = request.POST.get("movement_type")
            quantity = request.POST.get("quantity")
            selling_amount = request.POST.get("selling_amount") or None
            notes = request.POST.get("notes") or ""
            payment_method = request.POST.get("payment_method") or None

            if not product_id or not branch_id or not movement_type or not quantity:
                messages.error(request, "All required fields must be filled.")
                return redirect("stock_movement_view")

            # ---------- STAFF BRANCH RESTRICTION ----------
            if role == "staff":
                if not user.branch:
                    messages.error(request, "You are not assigned to any branch.")
                    return redirect("stock_movement_view")

                if int(branch_id) != user.branch.id:
                    messages.error(request, "You can only act on your assigned branch.")
                    return redirect("stock_movement_view")

            try:
                product = get_object_or_404(Product, id=product_id)
                branch = get_object_or_404(Branch, id=branch_id)
                quantity = int(quantity)

                # ---------- ADD ----------
                if action == "add":
                    StockMovement.objects.create(
                        product=product,
                        branch=branch,
                        movement_type=movement_type,
                        quantity=quantity,
                        selling_amount=selling_amount,
                        notes=notes,
                        payment_method=payment_method,
                        created_by=user
                    )
                    messages.success(request, "Stock movement recorded successfully.")

                # ---------- UPDATE ----------
                elif action == "update":
                    movement = get_object_or_404(StockMovement, id=int(movement_id))

                    # Staff can update ONLY their own records
                    if role == "staff" and movement.created_by != user:
                        messages.error(request, "You cannot edit this record.")
                        return redirect("stock_movement_view")

                    movement.product = product
                    movement.branch = branch
                    movement.movement_type = movement_type
                    movement.quantity = quantity
                    movement.selling_amount = selling_amount
                    movement.notes = notes
                    movement.payment_method = payment_method
                    movement.save()

                    messages.success(request, "Stock movement updated successfully.")

            except Exception as e:
                messages.error(request, str(e))

            return redirect("stock_movement_view")

        # ---------- DELETE ----------
        elif action == "delete":
            movement = get_object_or_404(StockMovement, id=int(movement_id))

            # Staff can delete ONLY their own records
            if role == "staff" and movement.created_by != user:
                messages.error(request, "You cannot delete this record.")
                return redirect("stock_movement_view")

            movement.delete()
            messages.success(request, "Stock movement deleted successfully.")
            return redirect("stock_movement_view")

        messages.error(request, "Invalid action.")
        return redirect("stock_movement_view")

    # -------------------- GET : VIEW MOVEMENTS --------------------
    now_kigali = timezone.now().astimezone(KIGALI_TZ)
    last_24_hours = now_kigali - timedelta(hours=24)

    if role == "admin":
        movements = StockMovement.objects.filter(
            created_at__gte=last_24_hours
        )

    elif role == "manager":
        movements = StockMovement.objects.filter(
            branch__account=user.account,
            created_at__gte=last_24_hours
        )

    else:  # staff → VIEW ALL activity in their branch
        movements = StockMovement.objects.filter(
            branch=user.branch,
            created_at__gte=last_24_hours
        )

    movements = movements.select_related(
        "product", "branch", "created_by"
    ).order_by("-id")

    # -------------------- DROPDOWNS --------------------
    if role == "admin":
        branches = Branch.objects.all()
        products = Product.objects.all()

    elif role == "manager":
        branches = Branch.objects.filter(account=user.account)
        products = Product.objects.filter(account=user.account)

    else:  # staff
        branches = Branch.objects.filter(id=user.branch.id)
        products = Product.objects.filter(branch=user.branch)

    # -------------------- RENDER --------------------
    return render(request, "stock_movement_list.html", {
        "movements": movements,
        "branches": branches,
        "products": products,
        "role": role,
        "user": user,
    })

# ---------- stock movement all records view section ----------
def stock_movement_all_records_view(request):
    # -------------------- LOGIN CHECK --------------------
    if not request.session.get('user_id') and not request.session.get('admin_id'):
        return redirect('login_view')

    role = request.session.get('role')
    user = None

    if role != "admin":
        user = get_object_or_404(UserInfo, id=request.session["user_id"])

    # -------------------- GET : VIEW ALL RECORDS --------------------
    if role == "admin":
        movements = StockMovement.objects.select_related(
            "product", "branch", "created_by"
        ).order_by("-id")

    elif role == "manager":
        movements = StockMovement.objects.filter(
            branch__account=user.account
        ).select_related(
            "product", "branch", "created_by"
        ).order_by("-id")

    else:  # staff → ALL activity in assigned branch
        if not user.branch:
            movements = StockMovement.objects.none()
        else:
            movements = StockMovement.objects.filter(
                branch=user.branch
            ).select_related(
                "product", "branch", "created_by"
            ).order_by("-id")

    # -------------------- DROPDOWNS --------------------
    if role == "admin":
        products = Product.objects.all()
        branches = Branch.objects.all()

    elif role == "manager":
        products = Product.objects.filter(account=user.account)
        branches = Branch.objects.filter(account=user.account)

    else:  # staff
        products = Product.objects.filter(branch=user.branch)
        branches = Branch.objects.filter(id=user.branch.id)

    # -------------------- RENDER --------------------
    return render(request, "stock_movement_list_all_records.html", {
        "movements": movements,
        "products": products,
        "branches": branches,
        "role": role,
        "user": user,
    })


# --- list current stocks ---
def stock_view(request):
    if not request.session.get('user_id') and not request.session.get('admin_id'):
        return redirect('login_view')

    if request.session.get("role") == "staff":
        messages.error(request, "Access denied.")
        return redirect("index")

    role = request.session.get('role')
    user = None
    branch = None

    if role != "admin":
        user = UserInfo.objects.get(id=request.session["user_id"])
        branch = (
            Branch.objects.filter(manager=user).first()
            if role == "manager"
            else user.branch
        )

    movements = (
        StockMovement.objects.all()
        if role == "admin"
        else StockMovement.objects.filter(branch=branch)
    )

    stock_summary = (
        movements
        .annotate(
            adjusted_quantity=Case(
                When(movement_type='IN', then=F('quantity')),
                When(movement_type='OUT', then=-F('quantity')),
                default=Value(0),
                output_field=IntegerField()
            )
        )
        .values(
            'product__name',
            'product__cost_price'
        )
        .annotate(
            stock=Sum('adjusted_quantity'),
            total_cost=ExpressionWrapper(
                Sum('adjusted_quantity') * F('product__cost_price'),
                output_field=DecimalField(max_digits=14, decimal_places=2)
            )
        )
        .order_by('product__name')
    )

    total_inventory_value = sum(
        item['total_cost'] or 0 for item in stock_summary
    )

    return render(request, 'stock_list.html', {
        'stock_summary': stock_summary,
        'total_inventory_value': total_inventory_value,
        'branch': branch,
        'role': role,
    })

# --- Report view ---
def report_view(request):
    # ---------- LOGIN CHECK ----------
    if not request.session.get('user_id') and not request.session.get('admin_id'):
        return redirect('login_view')

    role = request.session.get('role')
    user = None

    if role != "admin":
        user = get_object_or_404(UserInfo, id=request.session["user_id"])

    # ---------- DATE ----------
    selected_date = request.GET.get('date')
    report_date = selected_date if selected_date else timezone.now().date()

    # ---------- BRANCH FILTERING ----------
    if role == "admin":
        branches = Branch.objects.select_related('manager', 'account')

    elif role == "manager":
        branches = Branch.objects.filter(
            account=user.account
        ).select_related('manager')

    else:  # staff → ONLY assigned branch
        if not user.branch:
            branches = Branch.objects.none()
        else:
            branches = Branch.objects.filter(
                id=user.branch.id
            ).select_related('manager')

    # ---------- BUILD REPORT ----------
    branch_reports = []

    for branch in branches:
        movements = StockMovement.objects.filter(
            branch=branch,
            created_at__date=report_date
        )

        sales = movements.filter(movement_type='OUT')

        summary = sales.aggregate(
            total_sales=Sum('selling_amount'),
            total_profit=Sum('profit'),
            total_qty=Sum('quantity')
        )

        branch_reports.append({
            'branch': branch,
            'sales': sales,
            'summary': summary
        })

    return render(request, 'report.html', {
        'report_date': report_date,
        'branch_reports': branch_reports,
        'role': role,
        'user': user,
    })


# -------------------------
# CREATE ACCOUNT
# -------------------------

def create_user_account(request):
    if request.session.get("role") != "admin":
        messages.error(request, "Access denied.")
        return redirect("index")

    if request.method == "POST":
        account_name = request.POST.get("account_name")
        email = request.POST.get("email")

        # Check if account already exists
        if Account.objects.filter(name=account_name).exists():
            messages.error(request, "Account already exists.")
            return redirect("create_user_account")

        # Check if manager already exists
        if UserInfo.objects.filter(email=email).exists():
            messages.error(request, "User with this email already exists.")
            return redirect("create_user_account")

        try:
            with transaction.atomic():
                account = Account.objects.create(
                    name=account_name,
                    phone=request.POST.get("account_phone"),
                    address=request.POST.get("account_address"),
                )

                manager = UserInfo.objects.create(
                    account=account,
                    firstname=request.POST.get("first_name"),
                    lastname=request.POST.get("last_name"),
                    email=email,
                    password=request.POST.get("password"),
                    role="manager",
                    is_active=True,
                )

                Branch.objects.create(
                    account=account,
                    branch_name=request.POST.get("branch_name"),
                    manager=manager,
                )

            messages.success(
                request,
                "Account, Manager, and Branch created successfully!"
            )
            return redirect("create_user_account")

        except Exception as e:
            messages.error(request, f"Error: {str(e)}")

    return render(request, "create_user_account.html")

def create_branch_with_manager(request):

    # LOGIN CHECK
    if not request.session.get("user_id"):
        return redirect("login_view")

    if request.session.get("role") != "manager":
        messages.error(request, "Access denied.")
        return redirect("index")

    account_id = request.session.get("account_id")
    if not account_id:
        messages.error(request, "Account not found in session.")
        return redirect("index")

    account = Account.objects.get(id=account_id)

    if request.method == "POST":
        branch_name = request.POST.get("branch_name")
        email = request.POST.get("email")

        # Check if branch already exists under this account
        if Branch.objects.filter(account=account, branch_name=branch_name).exists():
            messages.error(request, "Branch already exists for this account.")
            return redirect("create_branch_with_manager")

        # Check if manager already exists
        if UserInfo.objects.filter(email=email).exists():
            messages.error(request, "Manager with this email already exists.")
            return redirect("create_branch_with_manager")

        try:
            with transaction.atomic():

                manager = UserInfo.objects.create(
                    account=account,
                    firstname=request.POST.get("first_name"),
                    lastname=request.POST.get("last_name"),
                    email=email,
                    password=make_password(request.POST.get("password")),
                    role="manager",
                    is_active=True,
                )

                Branch.objects.create(
                    account=account,
                    branch_name=branch_name,
                    manager=manager,
                )

            messages.success(
                request,
                "Branch and Manager created successfully!"
            )
            return redirect("create_branch_with_manager")

        except Exception as e:
            messages.error(request, f"Error: {str(e)}")

    return render(request, "create_branch.html")



def create_staff_with_manager(request):

    # ===== AUTH CHECK =====
    if not request.session.get("user_id"):
        return redirect("login_view")

    if request.session.get("role") != "manager":
        messages.error(request, "Access denied.")
        return redirect("index")

    manager = UserInfo.objects.get(id=request.session["user_id"])

    # Manager's branch
    branch = Branch.objects.filter(manager=manager).first()
    if not branch:
        messages.error(request, "No branch assigned to you.")
        return redirect("index")

    # ===== HANDLE POST REQUEST =====
    if request.method == "POST":

        # ===== TOGGLE STAFF =====
        if request.POST.get("action") == "toggle":
            staff_id = request.POST.get("staff_id")
            staff = get_object_or_404(UserInfo, id=staff_id, role="staff", branch=branch)
            staff.is_active = not staff.is_active
            staff.save()
            status = "enabled" if staff.is_active else "disabled"
            messages.success(request, f"Staff {staff.firstname} {status} successfully.")
            return redirect("create_staff_with_manager")

        # ===== CREATE STAFF =====
        else:
            first_name = request.POST.get("first_name", "").strip()
            last_name = request.POST.get("last_name", "").strip()
            email = request.POST.get("email", "").strip()
            password = request.POST.get("password", "").strip()

            # ===== VALIDATION =====
            if not first_name:
                messages.error(request, "First name is required.")
                return redirect("create_staff_with_manager")
            if not last_name:
                messages.error(request, "Last name is required.")
                return redirect("create_staff_with_manager")
            if not email:
                messages.error(request, "Email is required.")
                return redirect("create_staff_with_manager")
            if not password:
                messages.error(request, "Password is required.")
                return redirect("create_staff_with_manager")

            if UserInfo.objects.filter(email=email).exists():
                messages.error(request, "Email already exists.")
                return redirect("create_staff_with_manager")

            try:
                with transaction.atomic():
                    UserInfo.objects.create(
                        account=manager.account,
                        branch=branch,
                        firstname=first_name,
                        lastname=last_name,
                        email=email,
                        password=make_password(password),
                        role="staff",
                        is_active=True,
                    )
                    messages.success(request, f"Staff {first_name} {last_name} created successfully.")

            except Exception as e:
                messages.error(request, f"Error creating staff: {str(e)}")

            return redirect("create_staff_with_manager")

    # ===== VIEW STAFF =====
    staff_list = UserInfo.objects.filter(role="staff", branch=branch).order_by("-id")

    return render(request, "create_staff.html", {
        "branch": branch,
        "staff_list": staff_list
    })


from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Count, Sum, F, Q, DecimalField, ExpressionWrapper, Value
from django.db.models.functions import Coalesce
from django.utils.timezone import now

from .models import Account, Branch, UserInfo, Stock

def settings_view(request):
    # ---------- AUTH ----------
    if not request.session.get("user_id") and not request.session.get("admin_id"):
        return redirect("login_view")

    role = request.session.get("role")
    if role == "staff":
        messages.error(request, "Access denied.")
        return redirect("index")

    account_id = request.session.get("account_id")

    # ---------- POST ----------
    if request.method == "POST":
        action = request.POST.get("action")

        # ===== ADMIN =====
        if action == "update_account" and role == "admin":
            account = get_object_or_404(Account, id=request.POST.get("account_id"))
            account.name = request.POST.get("name")
            account.phone = request.POST.get("phone")
            account.address = request.POST.get("address")
            account.save()
            messages.success(request, "Account updated successfully.")
            return redirect("settings_view")

        if action == "toggle_account" and role == "admin":
            account = get_object_or_404(Account, id=request.POST.get("account_id"))
            account.is_active = not account.is_active
            account.save()
            messages.success(request, f"Account {'enabled' if account.is_active else 'disabled'} successfully.")
            return redirect("settings_view")

        # ===== MANAGER =====
        if action == "update_branch" and role == "manager":
            branch = get_object_or_404(Branch, id=request.POST.get("branch_id"))
            if branch.account_id != account_id:
                messages.error(request, "Unauthorized branch.")
                return redirect("index")
            branch.branch_name = request.POST.get("branch_name")
            branch.save()
            messages.success(request, "Branch updated successfully.")
            return redirect("settings_view")

    # ---------- GET ----------
    context = {}

    if role == "admin":
        current_month = now().month
        current_year = now().year

        accounts = (
            Account.objects
            .annotate(
                total_users=Count("users"),
                managers_count=Count("users", filter=Q(users__role="manager")),
                staff_count=Count("users", filter=Q(users__role="staff")),
                branches_count=Count("branches"),
                products_count=Count("products"),
                stock_value=Coalesce(
                    Sum(
                        ExpressionWrapper(
                            F("products__stocks__quantity") * F("products__cost_price"),
                            output_field=DecimalField(max_digits=14, decimal_places=2),
                        )
                    ),
                    Value(0, output_field=DecimalField(max_digits=14, decimal_places=2)),
                ),
                monthly_sales=Coalesce(
                    Sum(
                        "products__movements__selling_amount",
                        filter=Q(
                            products__movements__movement_type="OUT",
                            products__movements__created_at__month=current_month,
                            products__movements__created_at__year=current_year,
                        ),
                    ),
                    Value(0, output_field=DecimalField(max_digits=14, decimal_places=2)),
                ),
            )
            .order_by("-id")
        )

        selected_account = accounts.first()

        context.update({
            "accounts": accounts,
            "account": selected_account,
            "branches": Branch.objects.filter(account=selected_account) if selected_account else [],
            "staff": UserInfo.objects.filter(account=selected_account, role="staff") if selected_account else [],
        })

    elif role == "manager":
        account = get_object_or_404(Account, id=account_id)

        branches = (
            Branch.objects.filter(account=account)
            .select_related("manager")
            .prefetch_related("products__stocks")
        )

        staff = UserInfo.objects.filter(account=account, role="staff")

        branch_stock = {}
        for branch in branches:
            total = Stock.objects.filter(branch=branch).aggregate(
                total=Coalesce(
                    Sum(
                        ExpressionWrapper(
                            F("quantity") * F("product__cost_price"),
                            output_field=DecimalField(max_digits=14, decimal_places=2),
                        )
                    ),
                    Value(0, output_field=DecimalField(max_digits=14, decimal_places=2)),
                )
            )["total"]
            branch_stock[branch.id] = total

        context.update({
            "account": account,
            "branches": branches,
            "staff": staff,
            "branch_stock": branch_stock,
        })

    return render(request, "settings.html", context)



def forgot_password_otp(request):
    if request.method == "POST":
        email = request.POST.get("email")

        user = UserInfo.objects.filter(email=email).first()
        admin = AdminInfo.objects.filter(email=email).first()

        if not user and not admin:
            messages.error(request, "Email not found")
            return redirect("forgot-password-otp")

        PasswordResetOTP.objects.filter(email=email).delete()

        otp = PasswordResetOTP.generate_otp()
        PasswordResetOTP.objects.create(email=email, otp=otp)

        send_mail(
            "Your Password Reset OTP",
            f"Your OTP is {otp}. It expires in 10 minutes.",
            settings.DEFAULT_FROM_EMAIL,
            [email],
        )

        request.session["reset_email"] = email
        messages.success(request, "OTP sent to your email")
        return redirect("verify-otp")

    return render(request, "auth-forgot-password.html")


def is_strong_password(password):
    return (
        len(password) >= 8 and
        re.search(r"[A-Z]", password) and
        re.search(r"[a-z]", password) and
        re.search(r"\d", password) and
        re.search(r"[!@#$%^&*]", password)
    )

def verify_otp(request):
    email = request.session.get("reset_email")
    if not email:
        return redirect("forgot-password-otp")

    if request.method == "POST":
        otp_input = request.POST.get("otp")
        password = request.POST.get("password")
        confirm = request.POST.get("confirm")

        record = PasswordResetOTP.objects.filter(
            email=email, otp=otp_input
        ).first()

        if not record:
            messages.error(request, "Invalid OTP")
            return redirect("verify-otp")

        if record.is_expired():
            record.delete()
            messages.error(request, "OTP expired")
            return redirect("forgot-password-otp")

        if password != confirm:
            messages.error(request, "Passwords do not match")
            return redirect("verify-otp")

        if not is_strong_password(password):
            messages.error(
                request,
                "Password must be 8+ chars with uppercase, lowercase, number & symbol"
            )
            return redirect("verify-otp")

        user = UserInfo.objects.filter(email=email).first()
        admin = AdminInfo.objects.filter(email=email).first()

        if user:
            user.set_password(password)
            user.save()
        elif admin:
            admin.set_password(password)
            admin.save()

        record.delete()
        del request.session["reset_email"]

        messages.success(request, "Password reset successfully")
        return redirect("login_view")

    return render(request, "auth-reset_password.html")


def resend_otp(request):
    email = request.session.get("reset_email")
    if not email:
        return JsonResponse({"error": "Session expired"}, status=400)

    PasswordResetOTP.objects.filter(email=email).delete()

    otp = PasswordResetOTP.generate_otp()
    PasswordResetOTP.objects.create(email=email, otp=otp)

    send_mail(
        "Your Password Reset OTP",
        f"Your OTP is {otp}. It expires in 10 minutes.",
        settings.DEFAULT_FROM_EMAIL,
        [email],
    )

    return JsonResponse({"success": "OTP resent"})