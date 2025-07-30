from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()

class Command(BaseCommand):
    help = 'Check and update user admin status'

    def handle(self, *args, **options):
        username = input("Enter username to check: ")
        try:
            user = User.objects.get(username=username)
            print(f"\nUser: {user.username}")
            print(f"Is Admin: {user.is_admin}")
            print(f"Is Op: {user.is_op}")
            print(f"Is Rs: {user.is_rs}")
            
            if input("\nDo you want to make this user an admin? (y/n): ").lower() == 'y':
                user.is_admin = True
                user.save()
                print(f"{user.username} is now an admin!")
        except User.DoesNotExist:
            print(f"User '{username}' not found.")
