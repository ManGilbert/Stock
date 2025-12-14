from .models import UserInfo

def user_account_info(request):
    """
    Provide account_name and branch_name in all templates.
    """
    account_name = None
    branch_name = None

    if request.session.get('admin_id'):
        account_name = "Admin"
        branch_name = "-"
    elif request.session.get('user_id'):
        try:
            user = UserInfo.objects.get(id=request.session.get('user_id'))
            account_name = user.account.name if user.account else "No Account"
            branch = user.account.branches.first() if user.account else None
            branch_name = branch.branch_name if branch else "No Branch"
        except UserInfo.DoesNotExist:
            account_name = "Unknown Account"
            branch_name = "Unknown Branch"

    return {
        'account_name': account_name,
        'branch_name': branch_name
    }
