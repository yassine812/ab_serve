from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from Gamme.models import profile

class Command(BaseCommand):
    help = 'Create profiles for all existing users'

    def handle(self, *args, **options):
        users = User.objects.all()
        for user in users:
            if not hasattr(user, 'profile'):
                profile.objects.create(user=user)
                self.stdout.write(self.style.SUCCESS(f'Created profile for {user.username}'))
