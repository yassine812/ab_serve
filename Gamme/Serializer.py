from rest_framework import serializers
from .models import GammeControle, MissionControle, OperationControle, PhotoOperation
from django.contrib.auth.models import User

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'role']

#GammeControle
class GammeControleSerializer(serializers.ModelSerializer):
    class Meta:
        model = GammeControle
        fields = '__all__'

#MissionControle
class MissionControleSerializer(serializers.ModelSerializer):
    class Meta:
        model = MissionControle
        fields = '__all__'

#OperationControle
class OperationControleSerializer(serializers.ModelSerializer):
    class Meta:
        model = OperationControle
        fields = '__all__'

#PhotoOperation
class PhotoOperationSerializer(serializers.ModelSerializer):
    class Meta:
        model = PhotoOperation
        fields = '__all__'
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'role']


