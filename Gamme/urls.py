from django.urls import path
from .views import (GammeControleCreateView, GammeControleDetailView, GammeControleListView, GammeControleUpdateView, GammeControleDeleteView, view_gamme_pdf, 
                    MissionControleCreateView, MissionControleListView, MissionControleUpdateView, MissionControleDeleteView,
                    OperationControleCreateView, OperationControleListView, OperationControleUpdateView, OperationControleDeleteView,
                    OperationControleDetailView, EpiListView, EpiCreateView, EpiUpdateView, EpiDeleteView,
                    PhotoOperationCreateView, PhotoOperationListView, PhotoOperationUpdateView, PhotoOperationDeleteView,
                    UserListView, UserUpdateView, OperatorDashboardView, op_edit, UserDeleteView, DashboardView, ProfileView, 
                    login, logoutView, RegisterView, ajouter_utilisateur, save_mission_pdf, upload_photo_defaut, delete_photo_defaut,
                    MoyenControleListView, MoyenControleCreateView, MoyenControleUpdateView, MoyenControleDeleteView, check_mission_code,
                    validate_gamme)
app_name = 'Gamme'
urlpatterns = [
    path('gamme/gammecontrole/create/', GammeControleCreateView.as_view(), name='gammecontrole_create'),
    path('gamme/gammecontrole/list/', GammeControleListView.as_view(), name='gammecontrole_list'),
    path('gamme/gammecontrole/update/<int:pk>/', GammeControleUpdateView.as_view(), name='gammecontrole_update'),
    path('gamme/gammecontrole/delete/<int:pk>/', GammeControleDeleteView.as_view(), name='gammecontrole_delete'),
    
    path('gamme/missioncontrole/create/', MissionControleCreateView.as_view(), name='missioncontrole_create'),
    path('gamme/missioncontrole/list/', MissionControleListView.as_view(), name='missioncontrole_list'),
    path('gamme/missioncontrole/update/<int:pk>/', MissionControleUpdateView.as_view(), name='missioncontrole_update'),
    path('gamme/missioncontrole/delete/<int:pk>/', MissionControleDeleteView.as_view(), name='missioncontrole_delete'),
    
    path('gamme/operationcontrole/create/', OperationControleCreateView.as_view(), name='operationcontrole_create'),
    path('gamme/operationcontrole/list/', OperationControleListView.as_view(), name='operationcontrole_list'),
    path('gamme/operationcontrole/<int:pk>/', OperationControleDetailView.as_view(), name='operationcontrole_detail'),
    path('gamme/operationcontrole/<int:pk>/update/', OperationControleUpdateView.as_view(), name='operationcontrole_update'),
    path('gamme/operationcontrole/<int:pk>/delete/', OperationControleDeleteView.as_view(), name='operationcontrole_delete'),
   
    path('gamme/photooperation/create/', PhotoOperationCreateView.as_view(), name='photooperation_create'),
    path('gamme/photooperation/list/', PhotoOperationListView.as_view(), name='photooperation_list'),
    path('gamme/photooperation/update/<int:pk>/', PhotoOperationUpdateView.as_view(), name='photooperation_update'),
    path('gamme/photooperation/delete/<int:pk>/', PhotoOperationDeleteView.as_view(), name='photooperation_delete'),

    path('gamme/ajouter_utilisateur/', ajouter_utilisateur.as_view(), name='ajouter_utilisateur'),
    path('gamme/user/list/', UserListView.as_view(), name='user_list'),
    path('gamme/user/update/<int:pk>/', UserUpdateView.as_view(), name='user_update'),
    path('gamme/user/delete/<int:pk>/', UserDeleteView.as_view(), name='user_delete'),
    path('gamme/dashboard/', DashboardView.as_view(), name='dashboard'),
    path('gamme/operateur-dashboard/', OperatorDashboardView.as_view(), name='operateur_dashboard'),
    path('gamme/op_edit/<int:pk>/', op_edit.as_view(), name='op_edit'),
    
    path('gamme/profile/', ProfileView.as_view(), name='profile'),
    path('login/', login.as_view(), name='login'),
    path('logout/', logoutView.as_view(), name='logout'),
    path('register/', RegisterView.as_view(), name='register'),
    # URL for viewing the PDF in browser
    path('gamme/pdf/<int:mission_id>/', view_gamme_pdf, name='view_gamme_pdf'),
    # URL for saving PDF to server
    path('gamme/missioncontrole/<int:mission_id>/save-pdf/', save_mission_pdf, name='save_mission_pdf'),
    
    # Gamme validation URL
    path('gamme/gamme/<int:gamme_id>/validate/', validate_gamme, name='validate_gamme'),
    
    # Photo defaut URLs
    path('gamme/photo-defaut/upload/', upload_photo_defaut, name='upload_photo_defaut'),
    path('gamme/photo-defaut/<int:photo_id>/delete/', delete_photo_defaut, name='delete_photo_defaut'),
    
    # EPI URLs
    path('gamme/epi/', EpiListView.as_view(), name='epi_list'),
    path('gamme/epi/create/', EpiCreateView.as_view(), name='epi_create'),
    path('gamme/epi/update/<int:pk>/', EpiUpdateView.as_view(), name='epi_update'),
    path('gamme/epi/delete/<int:pk>/', EpiDeleteView.as_view(), name='epi_delete'),
    
    # Moyens de contrôle URLs
    path('gamme/moyens-controle/', MoyenControleListView.as_view(), name='moyencontrole_list'),
    path('gamme/moyens-controle/create/', MoyenControleCreateView.as_view(), name='moyencontrole_create'),
    path('gamme/moyens-controle/update/<int:pk>/', MoyenControleUpdateView.as_view(), name='moyencontrole_update'),
    path('gamme/moyens-controle/delete/<int:pk>/', MoyenControleDeleteView.as_view(), name='moyencontrole_delete'),

    # API URLs
    path('gamme/api/check-mission-code/', check_mission_code, name='check_mission_code'),
]