from rest_framework import serializers
from .models import GammeControle, MissionControle, OperationControle, PhotoOperation, PhotoDefaut, validation, epi, moyens_controle
from django.contrib.auth.models import User

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'role']

#PhotoDefaut
class PhotoDefautSerializer(serializers.ModelSerializer):
    class Meta:
        model = PhotoDefaut
        fields = '__all__'

#Validation
class ValidationSerializer(serializers.ModelSerializer):
    class Meta:
        model = validation
        fields = '__all__'

#EPI
class EpiSerializer(serializers.ModelSerializer):
    class Meta:
        model = epi
        fields = '__all__'

#MoyensControle
class MoyensControleSerializer(serializers.ModelSerializer):
    class Meta:
        model = moyens_controle
        fields = '__all__'

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
class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = '__all__'


