from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import AdminInfo, UserInfo, Account, Branch, Product
from django.contrib.auth.hashers import make_password, check_password


from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import StockMovement, Product, Branch, UserInfo

from django.shortcuts import render, redirect
from django.db.models import Sum, F, Case, When, Value, IntegerField, ExpressionWrapper,DecimalField
from .models import StockMovement, UserInfo, Branch

from django.shortcuts import render, redirect
from django.utils import timezone
from datetime import timedelta
from django.db.models import Sum
from .models import StockMovement, UserInfo, Branch

# ---------- Send logged user to index ----------
def index(request):
    """Send logged user to dashboard"""
    if request.session.get('admin_id') or request.session.get('user_id'):
        return render(request, 'index.html')
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

        # SESSION
        request.session["admin_id"] = user.id
        request.session["role"] = "admin"
        request.session["user_name"] = user.firstname

        # 30-minute Auto Expire
        request.session.set_expiry(1800)

        messages.success(request, "Logged in successfully!")
        return redirect("index")

    # ------------------- USER LOGIN ---------------------
    elif user_type == "user":
        user = _authenticate_user(email, password)
        if not user:
            messages.error(request, "Invalid user email or password.")
            return render(request, "auth-login.html")

        if not user.is_active:
            messages.error(request, "Your account is disabled.")
            return render(request, "auth-login.html")

        # Determine branch info
        branch_name = None
        branch_id = None

        if user.role == "manager":
            branch = Branch.objects.filter(manager=user).first()
            if branch:
                branch_name = branch.branch_name
                branch_id = branch.id
        else:  # For staff or other roles
            branch = Branch.objects.filter(account=user.account).first()
            if branch:
                branch_name = branch.branch_name
                branch_id = branch.id

        # SESSION
        request.session["user_id"] = user.id
        request.session["role"] = user.role
        request.session["account_id"] = user.account.id if user.account else None
        request.session["user_name"] = user.firstname
        request.session["branch_name"] = branch_name
        request.session["branch_id"] = branch_id

        # 30-minute Auto Expire
        request.session.set_expiry(1800)

        messages.success(request, "Logged in successfully!")
        return redirect("index")

    # Unexpected
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


def logout_view(request):
    request.session.flush()
    return redirect('login_view')

# ---------- product section ----------
def products_view(request):
    # Check login
    if not request.session.get('user_id') and not request.session.get('admin_id'):
        return redirect('login_view')

    role = request.session.get('role')
    user = None

    if role == "admin":
        products = Product.objects.all().order_by("-id")
    else:
        user = UserInfo.objects.get(id=request.session["user_id"])
        products = Product.objects.filter(account=user.account).order_by("-id")


    # Handle POST actions
    if request.method == "POST":
        action = request.POST.get("action")

        # --- Add Product ---
        if action == "add":
            name = request.POST.get("name")
            branch_id = request.POST.get("branch")
            category = request.POST.get("category")
            cost_price = request.POST.get("cost_price")
            selling_price = request.POST.get("selling_price")

            if not branch_id:
                messages.error(request, "Please select a branch.")
            else:
                try:
                    branch = Branch.objects.get(id=branch_id, account=user.account)
                    Product.objects.create(
                        account=branch.account,
                        branch=branch,
                        name=name,
                        category=category,
                        cost_price=cost_price,
                        selling_price=selling_price
                    )
                    messages.success(request, f"Product '{name}' added successfully.")
                except Branch.DoesNotExist:
                    messages.error(request, "Invalid branch selected.")

        # --- Update Product ---
        elif action == "update":
            product_id = request.POST.get("product_id")
            if not product_id or not product_id.isdigit():
                messages.error(request, "Invalid product ID.")
                return redirect("products")

            product = get_object_or_404(Product, id=int(product_id), account=user.account)

            branch_id = request.POST.get("branch")
            try:
                branch = Branch.objects.get(id=branch_id, account=user.account)
                product.branch = branch
                product.name = request.POST.get("name")
                product.category = request.POST.get("category")
                product.cost_price = request.POST.get("cost_price")
                product.selling_price = request.POST.get("selling_price")
                product.save()
                messages.success(request, f"Product '{product.name}' updated successfully.")
            except Branch.DoesNotExist:
                messages.error(request, "Invalid branch selected.")

        # --- Delete Product ---
        elif action == "delete":
            product_id = request.POST.get("product_id")
            if not product_id or not product_id.isdigit():
                messages.error(request, "Invalid product ID.")
                return redirect("products")

            product = get_object_or_404(Product, id=int(product_id), account=user.account)
            product_name = product.name
            product.delete()
            messages.success(request, f"Product '{product_name}' deleted successfully.")

        else:
            messages.error(request, "Invalid action.")

        return redirect("products")

    # GET request: display products
    products = products.select_related('branch')

    return render(request, 'product_list.html', {
        'products': products,
        'role': role,
        'user': user  # make sure we pass user for the branch dropdown
    })


# --- stock movement view section ---
try:
    from zoneinfo import ZoneInfo
    KIGALI_TZ = ZoneInfo("Africa/Kigali")
except ImportError:
    import pytz
    KIGALI_TZ = pytz.timezone("Africa/Kigali")


def stock_movement_view(request):
    # --- LOGIN CHECK ---
    if not request.session.get('user_id') and not request.session.get('admin_id'):
        return redirect('login_view')

    role = request.session.get('role')
    user = None
    if role != "admin":
        user = UserInfo.objects.get(id=request.session["user_id"])

    # --- Handle POST actions ---
    if request.method == "POST":
        action = request.POST.get("action")
        movement_id = request.POST.get("movement_id")  # For update/delete

        if action in ["add", "update"]:
            product_id = request.POST.get("product")
            branch_id = request.POST.get("branch")
            movement_type = request.POST.get("movement_type")
            quantity = request.POST.get("quantity")
            selling_amount = request.POST.get("selling_amount") or None
            notes = request.POST.get("notes") or ""
            payment_method = request.POST.get("payment_method") or None

            # Validation for add/update only
            if not product_id or not branch_id or not movement_type or not quantity:
                messages.error(request, "All fields are required.")
                return redirect("stock_movement_view")

            try:
                product = Product.objects.get(id=product_id)
                branch = Branch.objects.get(id=branch_id)
                quantity = int(quantity)

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
                    messages.success(
                        request,
                        f"{movement_type} movement of {quantity} units for {product.name} recorded successfully."
                    )

                elif action == "update":
                    if not movement_id:
                        messages.error(request, "Invalid movement ID.")
                        return redirect("stock_movement_view")

                    movement = get_object_or_404(StockMovement, id=int(movement_id))
                    movement.product = product
                    movement.branch = branch
                    movement.movement_type = movement_type
                    movement.quantity = quantity
                    movement.selling_amount = selling_amount
                    movement.notes = notes
                    movement.payment_method = payment_method
                    movement.save()
                    messages.success(request, f"Stock movement updated successfully.")

            except (Product.DoesNotExist, Branch.DoesNotExist):
                messages.error(request, "Invalid product or branch selected.")
            except Exception as e:
                messages.error(request, str(e))

        elif action == "delete":
            if not movement_id:
                messages.error(request, "Invalid movement ID.")
                return redirect("stock_movement_view")

            movement = get_object_or_404(StockMovement, id=int(movement_id))
            movement.delete()
            messages.success(request, "Stock movement deleted successfully.")

        else:
            messages.error(request, "Invalid action.")

        return redirect("stock_movement_view")

    # --- GET request: list last 24 hours movements ---
    now_kigali = timezone.now().astimezone(KIGALI_TZ)
    last_24_hours = now_kigali - timedelta(hours=1)

    if role == "admin":
        movements = StockMovement.objects.filter(
            created_at__gte=last_24_hours
        )
    else:
        movements = StockMovement.objects.filter(
            branch__account=user.account,
            created_at__gte=last_24_hours
        )

    movements = movements.select_related("product", "branch", "created_by").order_by("-id")

    # --- Dropdown data ---
    products = Product.objects.filter(account=user.account) if user else Product.objects.all()
    branches = Branch.objects.filter(account=user.account) if user else Branch.objects.all()

    return render(request, "stock_movement_list.html", {
        "movements": movements,
        "products": products,
        "branches": branches,
        "role": role,
        "user": user
    })

# --- stock movement all records view ---
def stock_movement_all_records_view(request):
    # --- Check login ---
    if not request.session.get('user_id') and not request.session.get('admin_id'):
        return redirect('login_view')

    role = request.session.get('role')
    user = None
    if role != "admin":
        user = UserInfo.objects.get(id=request.session["user_id"])

    # --- GET request: list movements ---
    if role == "admin":
        movements = StockMovement.objects.select_related('product', 'branch', 'created_by').order_by("-id")
    else:
        movements = StockMovement.objects.filter(branch__account=user.account)\
                                         .select_related('product', 'branch', 'created_by')\
                                         .order_by("-id")

    products = Product.objects.filter(account=user.account) if user else Product.objects.all()
    branches = Branch.objects.filter(account=user.account) if user else Branch.objects.all()

    return render(request, "stock_movement_list_all_records.html", {
        "movements": movements,
        "products": products,
        "branches": branches,
        "role": role,
        "user": user
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

# ---------- daily report ----------
def report_view(request):
    # ---------- LOGIN CHECK ----------
    if not request.session.get('user_id') and not request.session.get('admin_id'):
        return redirect('login_view')

    role = request.session.get('role')
    account_id = request.session.get('account_id')

    # ---------- DATE ----------
    selected_date = request.GET.get('date')
    if selected_date:
        report_date = selected_date
    else:
        report_date = timezone.now().date()

    # ---------- BRANCHES ----------
    if role == "admin":
        branches = Branch.objects.select_related('manager', 'account')
    else:
        branches = Branch.objects.filter(account_id=account_id)\
                                 .select_related('manager')

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
    })

# -------------------------
# CREATE ACCOUNT
# -------------------------

def create_user_account(request):
    if request.session.get("role") != "admin":
        messages.error(request, "Access denied.")
        return redirect("index")

    if request.method == "POST":
        try:
            with transaction.atomic():

                account = Account.objects.create(
                    name=request.POST.get("account_name"),
                    phone=request.POST.get("account_phone"),
                    address=request.POST.get("account_address"),
                )

                manager = UserInfo.objects.create(
                    account=account,
                    firstname=request.POST.get("first_name"),
                    lastname=request.POST.get("last_name"),
                    email=request.POST.get("email"),
                    password=request.POST.get("password"),
                    role="manager",
                    is_active=True,
                )

                Branch.objects.create(
                    account=account,
                    branch_name=request.POST.get("branch_name"),
                    manager=manager,
                )

            # OUTSIDE transaction.atomic()
            messages.success(
                request,
                "Account, Manager, and Branch created successfully!"
            )
            return redirect("create_user_account")

        except Exception as e:
            messages.error(request, f"Error: {str(e)}")

    return render(request, "create_user_account.html")


def create_branch_with_manager(request):

    # LOGIN CHECK (manual, since no Django auth)
    if not request.session.get("user_id"):
        return redirect("login_view")

    if request.session.get("role") != "manager":
        messages.error(request, "Access denied.")
        return redirect("index")

    # Get account from session
    account_id = request.session.get("account_id")

    if not account_id:
        messages.error(request, "Account not found in session.")
        return redirect("index")

    account = Account.objects.get(id=account_id)

    if request.method == "POST":
        try:
            with transaction.atomic():

                manager = UserInfo.objects.create(
                    account=account,
                    firstname=request.POST.get("first_name"),
                    lastname=request.POST.get("last_name"),
                    email=request.POST.get("email"),
                    password=make_password(request.POST.get("password")),
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
                "Branch and Manager created successfully!"
            )
            return redirect("create_branch_with_manager")

        except Exception as e:
            messages.error(request, f"Error: {str(e)}")

    return render(request, "create_branch.html")


def create_staff_with_manager(request):

    # AUTH CHECK
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

    # ================= CREATE STAFF =================
    if request.method == "POST":
        try:
            with transaction.atomic():

                email = request.POST.get("email")

                if UserInfo.objects.filter(email=email).exists():
                    messages.error(request, "Email already exists.")
                    return redirect("create_staff_with_manager")

                UserInfo.objects.create(
                    account=manager.account,
                    branch=branch,  # FIXED
                    firstname=request.POST.get("first_name"),
                    lastname=request.POST.get("last_name"),
                    email=email,
                    password=make_password(request.POST.get("password")),
                    role="staff",
                    is_active=True,
                )

                messages.success(request, "Staff created successfully.")

        except Exception as e:
            messages.error(request, str(e))

        return redirect("create_staff_with_manager")

    # ================= VIEW STAFF =================
    staff_list = UserInfo.objects.filter(
        role="staff",
        branch=branch
    ).order_by("-id")

    return render(request, "create_staff.html", {
        "branch": branch,
        "staff_list": staff_list
    })


