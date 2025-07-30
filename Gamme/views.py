from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
import os
import logging
from django.views.generic import ListView,DetailView, CreateView, UpdateView, DeleteView, View, TemplateView
from django.urls import reverse_lazy
from django.contrib import messages
from django.forms import inlineformset_factory
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from .models import MissionControle, GammeControle, OperationControle, PhotoOperation, PhotoDefaut, User
from .forms import MissionControleForm, GammeControleForm,ProfileUpdateForm, OperationControleForm,OperationControleFormSet, PhotoOperationForm, UpdateGammeFormSet, UpdateOperationFormSet, UpdatePhotoFormSet,RegisterForm
from django.contrib.auth import logout
from django.views import View
from django.contrib.auth.views import LoginView
gammeFormSet = inlineformset_factory(   
    MissionControle,
    GammeControle,
    fields=['intitule', 'version', 'statut'],
    extra=0,
    can_delete=True
)
class MissionControleUpdateView(LoginRequiredMixin,View):
    template_name = 'gamme/missioncontrole_update.html'

    def get(self, request, pk):
        missioncontrole = get_object_or_404(MissionControle, pk=pk)
        operation_formset = OperationControleFormSet(prefix='form', queryset=OperationControle.objects.none())
        # Sort gammes by last update date in descending order
        gammes = GammeControle.objects.filter(mission=missioncontrole).order_by('-date_mise_a_jour')
        return render(request, self.template_name, {
            'missioncontrole': missioncontrole,
            'gammes': gammes,
            'operation_formset': operation_formset,
        })

    def post(self, request, pk):
        missioncontrole = get_object_or_404(MissionControle, pk=pk)

        # --- Mise à jour des champs mission ---
        missioncontrole.code = request.POST.get('code')
        missioncontrole.intitule = request.POST.get('intitule')
        missioncontrole.produitref = request.POST.get('produitref')
        missioncontrole.statut = request.POST.get('statut') == 'True'
        missioncontrole.save()

        # --- Mise à jour des gammes et opérations ---
        gammes = GammeControle.objects.filter(mission=missioncontrole)
        for gamme in gammes:
            intitule = request.POST.get(f'{gamme.id}-intitule', gamme.intitule)
            statut = request.POST.get(f'{gamme.id}-statut', 'False')
            changement_detecte = False

            if intitule != gamme.intitule or (statut == 'True') != gamme.statut:
                changement_detecte = True

            for op in gamme.operationcontrole_set.all():
                titre = request.POST.get(f"{op.id}-titre", op.titre)
                ordre = request.POST.get(f"{op.id}-ordre", op.ordre)
                description = request.POST.get(f"{op.id}-description", op.description)
                criteres = request.POST.get(f"{op.id}-criteres", op.criteres)

                if titre != op.titre or str(ordre) != str(op.ordre) or description != op.description or criteres != op.criteres:
                    changement_detecte = True

                # Photos existantes
                for photo in op.photooperation_set.all():
                    desc = request.POST.get(f"photo_{photo.id}_description", photo.description)
                    delete = request.POST.get(f"photo_{photo.id}_DELETE", None)
                    if desc != photo.description or delete is not None:
                        changement_detecte = True

                # Nouvelles photos dynamiques ?
                for key in request.FILES.keys():
                    if key.startswith(f'photo_{op.id}_'):
                        changement_detecte = True
                        break

            # Ajout d'opérations ?
            for key in request.POST.keys():
                if key.startswith(f"newop_{gamme.id}_"):
                    changement_detecte = True
                    break

            # Fichiers liés aux nouvelles opérations ?
            for key in request.FILES.keys():
                if key.startswith("newphoto_") or key.startswith(f"newop_{gamme.id}_") or key.startswith("formop_"):
                    changement_detecte = True
                    break

            # Si changement → créer nouvelle version de la gamme
            if changement_detecte:
                previous_versions = GammeControle.objects.filter(mission=missioncontrole, intitule=gamme.intitule).order_by('-version')
                latest_version = float(previous_versions.first().version) if previous_versions.exists() else 1.0
                previous_versions.update(statut=False)
                next_version = round(latest_version + 0.1, 1)

                no_incident = request.POST.get(f'{gamme.id}-No_incident', gamme.No_incident)
                new_gamme = GammeControle.objects.create(
                    mission=missioncontrole,
                    intitule=intitule,
                    No_incident=no_incident,
                    statut=(statut == 'True'),
                    version=next_version,
                    created_by=request.user
                )

                # Copie des opérations existantes
                for op in gamme.operationcontrole_set.all():
                    new_op = OperationControle.objects.create(
                        gamme=new_gamme,
                        titre=op.titre,
                        ordre=op.ordre,
                        description=op.description,
                        criteres=op.criteres,
                        created_by=request.user
                    )

                    # Photos existantes copiées sauf celles à supprimer
                    for photo in op.photooperation_set.all():
                        if request.POST.get(f"photo_{photo.id}_DELETE"):
                            continue
                        PhotoOperation.objects.create(
                            operation=new_op,
                            image=photo.image,
                            description=request.POST.get(f"photo_{photo.id}_description", photo.description)
                        )

                    # Nouvelles photos dynamiques
                    i = 0
                    while True:
                        image_key = f'photo_{op.id}_{i}_image'
                        desc_key = f'photo_{op.id}_{i}_description'
                        if image_key in request.FILES:
                            image = request.FILES[image_key]
                            description = request.POST.get(desc_key, '')
                            PhotoOperation.objects.create(
                                operation=new_op,
                                image=image,
                                description=description
                            )
                            i += 1
                        else:
                            break

                # Nouvelles opérations manuelles
                i = 0
                while True:
                    titre = request.POST.get(f'newop_{gamme.id}_{i}_titre')
                    if not titre:
                        break
                    ordre = request.POST.get(f'newop_{gamme.id}_{i}_ordre', 0)
                    description = request.POST.get(f'newop_{gamme.id}_{i}_description', '')
                    criteres = request.POST.get(f'newop_{gamme.id}_{i}_criteres', '')

                    new_op = OperationControle.objects.create(
                        gamme=new_gamme,
                        titre=titre,
                        ordre=ordre,
                        description=description,
                        criteres=criteres,
                        created_by=request.user
                    )

                    j = 0
                    while True:
                        key_img = f'newop_{gamme.id}_{i}_photo_{j}_image'
                        key_desc = f'newop_{gamme.id}_{i}_photo_{j}_description'
                        if key_img in request.FILES:
                            PhotoOperation.objects.create(
                                operation=new_op,
                                image=request.FILES[key_img],
                                description=request.POST.get(key_desc, '')
                            )
                            j += 1
                        else:
                            break
                    i += 1

        # --- Création d'une nouvelle gamme complète ---
        gamme_intitule = request.POST.get('gamme_intitule')
        gamme_no_incident = request.POST.get('gamme_No_incident', '')
        gamme_statut = request.POST.get('gamme_statut')
        if gamme_intitule and gamme_statut:
            new_gamme = GammeControle.objects.create(
                mission=missioncontrole,
                intitule=gamme_intitule,
                No_incident=gamme_no_incident,
                statut=gamme_statut == 'True',
                created_by=request.user,
                version=1.0
            )

            operation_formset = OperationControleFormSet(request.POST, prefix='form')
            if operation_formset.is_valid():
                for index, form in enumerate(operation_formset):
                    operation = form.save(commit=False)
                    operation.gamme = new_gamme
                    operation.created_by = request.user
                    # Ensure ordre is set and is a valid integer
                    if not operation.ordre or not str(operation.ordre).isdigit():
                        operation.ordre = index + 1  # Default to form position if ordre is invalid
                    operation.save()

                    j = 0
                    while True:
                        key_img = f'formop_{index}_photo_{j}'
                        key_desc = f'formop_{index}_photo_{j}_description'
                        if key_img in request.FILES:
                            PhotoOperation.objects.create(
                                operation=operation,
                                image=request.FILES[key_img],
                                description=request.POST.get(key_desc, '')
                            )
                            j += 1
                        else:
                            break

        return redirect('Gamme:missioncontrole_list')


class DashboardView(LoginRequiredMixin, View):
    template_name = 'gamme/dashboard.html'

    def get_context_data(self, **kwargs):
        context = {
            'missions': MissionControle.objects.all(),
            'gammes': GammeControle.objects.all(),
            'form': GammeControleForm(),
            'operation_formset': UpdateOperationFormSet(queryset=OperationControle.objects.none(), prefix='operation_formset')
        }
        return context

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, self.get_context_data())

    def post(self, request, *args, **kwargs):
        form_type = request.POST.get("form_type")
        is_mission_creation = form_type == "mission"
        # Initialize forms
        mission_form = None
        gamme_form = None
        operation_formset = UpdateOperationFormSet(request.POST or None, request.FILES or None, 
                                                prefix='operation_formset', 
                                                queryset=OperationControle.objects.none())
        if form_type == "mission":
            mission_form = MissionControleForm(request.POST, request.FILES)
            
            if mission_form.is_valid():
                try:
                    with transaction.atomic():
                        # Save mission first
                        mission = mission_form.save(commit=False)
                        mission.created_by = request.user
                        mission.save()
                        
                        # Get gamme data from the form
                        gamme_intitule = request.POST.get("gamme_intitule")
                        if gamme_intitule:
                            # Create gamme linked to the mission
                            gamme = GammeControle.objects.create(
                                mission=mission,
                                intitule=gamme_intitule,
                                No_incident=request.POST.get("gamme_No_incident", ""),
                                statut=request.POST.get("gamme_statut", "True") == "True",
                                version="1.0",
                                created_by=request.user
                            )
                            
                            # Save operations if any
                            if operation_formset.is_valid():
                                self.save_operations(request, operation_formset, gamme)
                            
                            messages.success(request, "Mission, gamme et opérations enregistrées avec succès.")
                            
                            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                                return JsonResponse({
                                    'success': True,
                                    'gamme_created': True,
                                    'redirect_url': reverse('Gamme:missioncontrole_list')
                                })
                            return redirect("Gamme:missioncontrole_list")
                        else:
                            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                                return JsonResponse({
                                    'success': False,
                                    'error': 'Erreur dans le formulaire d\'opérations',
                                    'errors': dict(operation_formset.errors)
                                }, status=400)
                            messages.warning(request, "Mission enregistrée, mais certaines opérations n'ont pas pu être enregistrées.")
                            self.log_operation_formset_errors(operation_formset)
                except Exception as e:
                    error_msg = f"Erreur lors de la création de la gamme: {str(e)}"
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({
                            'success': False,
                            'error': error_msg
                        }, status=400)
                    messages.error(request, error_msg)
                else:
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({
                            'success': True,
                            'gamme_created': gamme_created,
                            'message': 'Mission enregistrée avec succès.'
                        })
                    messages.success(request, "Mission enregistrée avec succès.")
                    return redirect("Gamme:missioncontrole_list")

            else:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'error': 'Erreur de validation du formulaire',
                        'errors': dict(mission_form.errors)
                    }, status=400)
                for field, errors in mission_form.errors.items():
                    for error in errors:
                        messages.error(request, f"{field}: {error}")

        elif form_type == "gamme":
            gamme_form = GammeControleForm(request.POST, request.FILES)
            operation_formset = UpdateOperationFormSet(
                request.POST, 
                request.FILES, 
                prefix='operation_formset',
                queryset=OperationControle.objects.none()
            )
            
            if gamme_form.is_valid():
                try:
                    gamme = gamme_form.save(commit=False)
                    gamme.No_incident = request.POST.get("No_incident")
                    gamme.created_by = request.user
                    gamme.version = "1.0"
                    gamme.save()

                    if operation_formset.is_valid():
                        self.save_operations(request, operation_formset, gamme)
                        messages.success(request, "Gamme et opérations enregistrées avec succès.")
                        return redirect("Gamme:gammecontrole_list")
                    else:
                        messages.warning(request, "Gamme enregistrée, mais certaines opérations n'ont pas pu être enregistrées.")
                        self.log_operation_formset_errors(operation_formset)
                        
                except Exception as e:
                    messages.error(request, f"Erreur lors de l'enregistrement de la gamme: {str(e)}")
            else:
                for field, errors in gamme_form.errors.items():
                    for error in errors:
                        messages.error(request, f"{field}: {error}")

        else:
            messages.error(request, f"Type de formulaire non reconnu: {form_type}")
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'error': f'Type de formulaire non reconnu: {form_type}'
                }, status=400)
            return redirect('Gamme:dashboard')

        # Handle AJAX requests for form errors
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': 'Veuillez corriger les erreurs du formulaire.',
                'form_errors': dict(mission_form.errors if form_type == 'mission' else gamme_form.errors)
            }, status=400)
            
        # Prepare context for re-rendering the form with errors
        context = self.get_context_data()
        if form_type == 'gamme':
            context['form'] = gamme_form or GammeControleForm()
        else:
            context['form'] = GammeControleForm()
            
        context['operation_formset'] = operation_formset
        context['form_data'] = request.POST
        context['active_tab'] = form_type
        
        return render(request, self.template_name, context)

    def save_operations(self, request, formset, gamme):
        for i, form in enumerate(formset.forms):
            if form.is_valid() and form.cleaned_data.get('titre'):
                # Create the operation from the formset's data
                operation = OperationControle.objects.create(
                    gamme=gamme,
                    ordre=form.cleaned_data.get('ordre', i + 1),
                    titre=form.cleaned_data['titre'],
                    description=form.cleaned_data['description'],
                    criteres=form.cleaned_data['criteres'],
                    created_by=request.user
                )

                # Process file uploads for this operation
                for key, file_obj in request.FILES.items():
                    if key.startswith(f'operation_formset-{i}-photo_image'):
                        # Get the corresponding description
                        desc_key = key.replace('_image', '_description')
                        description = request.POST.get(desc_key, '')
                        
                        if file_obj:  # Only save if we have an actual file
                            try:
                                PhotoOperation.objects.create(
                                    operation=operation,
                                    image=file_obj,
                                    description=description,
                                    created_by=request.user
                                )
                            except Exception as e:
                                # Log the error but don't fail the entire operation
                                print(f"Error saving photo: {str(e)}")
                                messages.error(request, f"Erreur lors de l'enregistrement d'une photo: {str(e)}")

    def log_operation_formset_errors(self, formset):
        for i, form in enumerate(formset.forms):
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(self.request, f"Opération {i + 1} - {field}: {error}")

class GammeControleCreateView(LoginRequiredMixin,View):
    template_name = 'gamme/gammecontrole_create.html'

    def get(self, request):
        form = GammeControleForm()
        missions = MissionControle.objects.all()
        return render(request, self.template_name, {
            'form': form,
            'missions': missions
        })

    def post(self, request):
        form = GammeControleForm(request.POST, request.FILES)
        missions = MissionControle.objects.all()

        if not form.is_valid():
            messages.error(request, "Formulaire de la gamme invalide.")
            return render(request, self.template_name, {
                'form': form,
                'missions': missions
            })

        gamme = form.save(commit=False)
        gamme.created_by = request.user

        # Version initiale à 1.0 si non définie
        if not gamme.version:
            gamme.version = '1.0'

        mission_id = request.POST.get('mission')
        if mission_id:
            try:
                mission = MissionControle.objects.get(id=mission_id)
                gamme.mission = mission
            except MissionControle.DoesNotExist:
                messages.error(request, "Mission invalide sélectionnée.")
                return render(request, self.template_name, {
                    'form': form,
                    'missions': missions
                })
        else:
            messages.error(request, "Veuillez sélectionner une mission.")
            return render(request, self.template_name, {
                'form': form,
                'missions': missions
            })

        gamme.save()

        # Création des opérations liées, avec created_by
        op_index = 0
        while True:
            titre = request.POST.get(f'operation_{op_index}_titre')
            if not titre:
                break  # fin des opérations

            ordre = request.POST.get(f'operation_{op_index}_ordre') or 0
            description = request.POST.get(f'operation_{op_index}_description', '')
            criteres = request.POST.get(f'operation_{op_index}_criteres', '')

            operation = OperationControle.objects.create(
                gamme=gamme,
                titre=titre,
                ordre=int(ordre),
                description=description,
                criteres=criteres,
                created_by=request.user,   # IMPORTANT : assigner l'utilisateur ici
            )

            # Création des photos liées
            photo_index = 0
            while True:
                photo_key = f'photo_{op_index}_{photo_index}_image'
                desc_key = f'photo_{op_index}_{photo_index}_description'

                image = request.FILES.get(photo_key)
                description_photo = request.POST.get(desc_key, '')

                if not image:
                    break  # plus de photo

                PhotoOperation.objects.create(
                    operation=operation,
                    image=image,
                    description=description_photo
                )
                photo_index += 1

            op_index += 1

        messages.success(request, "La gamme, ses opérations et photos ont été enregistrées avec succès.")
        return redirect('Gamme:gammecontrole_list')

class GammeControleListView(LoginRequiredMixin, ListView):
    model = GammeControle
    template_name = 'gamme/gammecontrole_list.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['user'] = self.request.user 
        return context


class GammeControleUpdateView(LoginRequiredMixin,UpdateView):
    model = GammeControle
    template_name = 'gamme/gammecontrole_update.html'
    fields = ['mission', 'intitule', 'statut']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        OperationFormSet = inlineformset_factory(
            GammeControle,
            OperationControle,
            fields=('titre', 'ordre', 'description', 'criteres'),
            extra=0,
            can_delete=True,
        )

        if self.request.method == 'POST':
            operation_formset = OperationFormSet(self.request.POST, self.request.FILES, instance=self.object)
        else:
            operation_formset = OperationFormSet(instance=self.object)

        # Construire une liste (form, photos) pour chaque opération existante
        operation_forms_with_photos = []
        for form in operation_formset.forms:
            operation_instance = form.instance
            photos = PhotoOperation.objects.filter(operation=operation_instance) if operation_instance.pk else []
            operation_forms_with_photos.append({
                'form': form,
                'photos': photos,
            })

        context['operation_forms_with_photos'] = operation_forms_with_photos
        context['operation_formset'] = operation_formset
        context['missions'] = MissionControle.objects.all()

        return context

    def form_valid(self, form):
        context = self.get_context_data()
        operation_formset = context['operation_formset']
        if operation_formset.is_valid():
            self.object = form.save()
            operation_formset.instance = self.object
            operation_formset.save()
            return super().form_valid(form)
        else:
            return self.form_invalid(form)

class GammeControleDetailView(LoginRequiredMixin, DetailView):
    model = GammeControle
    template_name = 'gamme/gammecontrole_detail.html'
    context_object_name = 'gamme'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['operations'] = OperationControle.objects.filter(gamme=self.object).order_by('ordre')
        return context

class GammeControleDeleteView(LoginRequiredMixin,DeleteView):
    model = GammeControle
    template_name = 'gamme/gammecontrole_delete.html'
    success_url = reverse_lazy('Gamme:gammecontrole_list')


class MissionControleCreateView(LoginRequiredMixin,View):
    template_name = 'gamme/missioncontrole_create.html'

    def get(self, request):
        mission_form = MissionControleForm()
        return render(request, self.template_name, {
            'mission_form': mission_form,
        })

    def post(self, request):
        mission_form = MissionControleForm(request.POST)

        if mission_form.is_valid():
            mission = mission_form.save(commit=False)
            mission.created_by = request.user
            mission.save()

            # Il ne peut y avoir qu’une seule gamme (selon le JS)
            intitule = request.POST.get('gamme_0_intitule')
            if intitule:
                statut = request.POST.get('gamme_0_statut') == 'True'
                version = request.POST.get('gamme_0_version', '1.0')

                no_incident = request.POST.get('gamme_0_no_incident', '')
                gamme = GammeControle.objects.create(
                    mission=mission,
                    intitule=intitule,
                    No_incident=no_incident,
                    statut=statut,
                    version=version,
                    created_by=request.user
                )

                # Lire toutes les opérations associées à cette gamme
                operation_index = 0
                while True:
                    titre = request.POST.get(f'operation_0_{operation_index}_titre')
                    if not titre:
                        break

                    ordre = request.POST.get(f'operation_0_{operation_index}_ordre', 0)
                    description = request.POST.get(f'operation_0_{operation_index}_description', '')
                    criteres = request.POST.get(f'operation_0_{operation_index}_criteres', '')

                    operation = OperationControle.objects.create(
                        gamme=gamme,
                        titre=titre,
                        ordre=ordre,
                        description=description,
                        criteres=criteres,
                        created_by=request.user
                    )

                    # Lire les photos associées à cette opération
                    photo_index = 0
                    while True:
                        image = request.FILES.get(f'photo_0_{operation_index}_{photo_index}_image')
                        if not image:
                            break

                        photo_description = request.POST.get(
                            f'photo_0_{operation_index}_{photo_index}_description', '')

                        PhotoOperation.objects.create(
                            operation=operation,
                            image=image,
                            description=photo_description,
                            created_by=request.user
                        )

                        photo_index += 1

                    operation_index += 1

            messages.success(request, "Mission, gamme, opérations et photos enregistrées avec succès.")
            return redirect('Gamme:missioncontrole_list')

        # Si formulaire invalide
        messages.error(request, "Veuillez corriger les erreurs dans le formulaire.")
        return render(request, self.template_name, {
            'mission_form': mission_form,
        })

class MissionControleListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = MissionControle
    template_name = 'gamme/missioncontrole_list.html'
    
    def test_func(self):
        # Only allow access if user is admin, responsable, or operator
        return self.request.user.is_authenticated
    
    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        messages.error(self.request, "Accès refusé. Vous n'avez pas les droits nécessaires.")
        return redirect('Gamme:dashboard')

    def get_queryset(self):
        queryset = super().get_queryset()
        
        # For operators, only show active missions
        if self.request.user.is_op:
            queryset = queryset.filter(statut=True)
        else:
            # For admin/manager, apply filters if any
            statut = self.request.GET.get('statut')
            if statut == '1':
                queryset = queryset.filter(statut=True)
            elif statut == '0':
                queryset = queryset.filter(statut=False)
        
        # Apply product filter if provided
        produitref = self.request.GET.get('produitref')
        if produitref:
            queryset = queryset.filter(produitref__icontains=produitref)
            
        return queryset.order_by('-date_creation')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get unique product references for the filter dropdown
        produits = MissionControle.objects.values_list('produitref', flat=True).distinct()
        context['produits'] = sorted([p for p in produits if p and p.strip()])
        
        # Add filter values to context
        context['current_statut'] = self.request.GET.get('statut', '')
        context['current_produitref'] = self.request.GET.get('produitref', '')
        
        # Add user role to context for template logic
        context['is_operator'] = self.request.user.is_op
        
        return context

class MissionControleDeleteView(LoginRequiredMixin, DeleteView):
    model = MissionControle
    success_url = reverse_lazy('Gamme:missioncontrole_list')

class OperationControleCreateView(LoginRequiredMixin, View):
    template_name = 'gamme/operationcontrole_create.html'

    def get(self, request, *args, **kwargs):
        operation_form = OperationControleForm()
        return render(request, self.template_name, {
            'operation_form': operation_form,
        })

    def post(self, request, *args, **kwargs):
        operation_form = OperationControleForm(request.POST)

        if operation_form.is_valid():
            operation = operation_form.save(commit=False)
            operation.created_by = request.user
            operation.save()
            return redirect('Gamme:operationcontrole_list')
        
        return render(request, self.template_name, {
            'operation_form': operation_form,
        })

class OperationControleUpdateView(LoginRequiredMixin, UpdateView):
    model = OperationControle
    form_class = OperationControleForm
    template_name = 'gamme/operationcontrole_update.html'
    success_url = reverse_lazy('Gamme:operationcontrole_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['photos'] = PhotoOperation.objects.filter(operation=self.object).order_by('-id')
        return context

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        return super().form_valid(form)

class OperationControleListView(ListView,LoginRequiredMixin):
    model = OperationControle
    template_name = 'gamme/operationcontrole_list.html'

    def get_queryset(self):
        queryset = super().get_queryset()
        mission_id = self.kwargs.get('mission_id') or self.request.GET.get('mission')
        if mission_id:
            queryset = queryset.filter(mission_id=mission_id)
        return queryset.order_by('ordre')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        mission_id = self.request.GET.get('mission')
        if mission_id:
            context['mission'] = get_object_or_404(MissionControle, pk=mission_id)
        return context

class OperationControleDeleteView(DeleteView,LoginRequiredMixin):
    model = OperationControle
    template_name = 'gamme/operationcontrole_delete.html'
    success_url = reverse_lazy('Gamme:operationcontrole_list')

class OperationControleDetailView(DetailView,LoginRequiredMixin):
    model = OperationControle
    template_name = 'gamme/operationcontrole_detail.html'
    context_object_name = 'operation'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['photos'] = PhotoOperation.objects.filter(operation=self.object)
        if 'photo_form' not in context:
            context['photo_form'] = PhotoOperationForm()
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = PhotoOperationForm(request.POST, request.FILES)
        if form.is_valid():
            photo = form.save(commit=False)
            photo.operation = self.object
            photo.save()
            return redirect('Gamme:operationcontrole_detail', pk=self.object.pk)
        else:
            context = self.get_context_data(photo_form=form)
            return self.render_to_response(context)

# ----------- PHOTO OPERATION -----------

class PhotoOperationCreateView(LoginRequiredMixin,CreateView):
    model = PhotoOperation
    form_class = PhotoOperationForm
    template_name = None

    def form_valid(self, form):
        operation_id = self.request.POST.get('operation')
        form.instance.operation_id = operation_id
        form.instance.created_by = self.request.user
        form.instance.updated_by = self.request.user
        form.save()
        return redirect(reverse('Gamme:operationcontrole_update', kwargs={'pk': operation_id}))

    def get(self, request, *args, **kwargs):
        return redirect('Gamme:operationcontrole_list')

class PhotoOperationListView(LoginRequiredMixin, ListView):
    model = PhotoOperation
    template_name = 'gamme/photooperation_list.html'

    def get_queryset(self):
        return PhotoOperation.objects.all().order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['operations'] = OperationControle.objects.all()
        return context

class PhotoOperationUpdateView(LoginRequiredMixin,UpdateView):
    model = PhotoOperation
    form_class = PhotoOperationForm
    template_name = 'gamme/photooperation_update.html'

class PhotoOperationDeleteView(LoginRequiredMixin,DeleteView):
    model = PhotoOperation
    template_name = 'gamme/photooperation_delete.html'

    def get_success_url(self):
        return reverse_lazy('Gamme:operationcontrole_update', kwargs={'pk': self.object.operation.pk})




class OperatorDashboardView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = 'gamme/operateur_dashboard.html'
    
    def test_func(self):
        return self.request.user.is_op
    
    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        messages.error(self.request, "Accès refusé. Vous devez être un opérateur pour accéder à cette page.")
        return redirect('Gamme:dashboard')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Only show active missions to operators
        missions = MissionControle.objects.filter(statut=True)
        context['missions'] = missions
        context['missions_count'] = missions.count()
        context['active_missions_count'] = missions.count()  # Only active missions are shown
        return context


class UserListView(LoginRequiredMixin, ListView):
    model = User
    template_name = 'gamme/user_list.html'
    context_object_name = 'users'
    
    def get_queryset(self):
        # Get all users who are either opérateur, responsable, or RO
        return User.objects.filter(
            is_op=True
        ) | User.objects.filter(
            is_rs=True
        ) | User.objects.filter(
            is_ro=True
        ).order_by('username')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['user_count'] = self.get_queryset().count()
        return context

class UserUpdateView(LoginRequiredMixin, UpdateView):
    model = User
    fields = ['username', 'email', 'first_name', 'last_name']
    template_name = 'gamme/user_update.html'
    success_url = reverse_lazy('Gamme:user_list')

    def form_valid(self, form):
        user = form.save(commit=False)
        
        # Handle role selection
        role = self.request.POST.get('role')
        user.is_op = (role == 'op')
        user.is_rs = (role == 'rs')
        user.is_ro = (role == 'ro')
        
        user.save()
        messages.success(self.request, "L'utilisateur a été mis à jour avec succès.")
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.get_object()
        context['selected_role'] = 'op' if user.is_op else 'rs' if user.is_rs else 'ro' if user.is_ro else ''
        return context


class UserDeleteView(LoginRequiredMixin, DeleteView):
    model = User
    template_name = 'gamme/user_confirm_delete.html'
    success_url = reverse_lazy('Gamme:user_list')
    
    def delete(self, request, *args, **kwargs):
        user = self.get_object()
        if user == request.user:
            messages.error(request, "Vous ne pouvez pas supprimer votre propre compte.")
            return redirect(self.success_url)
            
        messages.success(request, f"L'utilisateur {user.username} a été supprimé avec succès.")
        return super().delete(request, *args, **kwargs)

class UserDeleteView(LoginRequiredMixin,DeleteView):
    model = User
    template_name = 'gamme/user_delete.html'
    success_url = reverse_lazy('Gamme:user_list')



class ProfileView(LoginRequiredMixin, View):
    template_name = 'gamme/profile.html'

    def get(self, request, *args, **kwargs):
        form = ProfileUpdateForm(instance=request.user)
        return render(request, self.template_name, {'form': form, 'user': request.user})

    def post(self, request, *args, **kwargs):
        form = ProfileUpdateForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profil mis à jour avec succès.')
            return redirect('Gamme:profile')
        messages.error(request, 'Erreur lors de la mise à jour du profil.')
        return render(request, self.template_name, {'form': form, 'user': request.user})

class logoutView(LoginRequiredMixin, View):
    def get(self, request):
        logout(request)
        messages.success(request, 'Déconnexion réussie.')
        return redirect('Gamme:login')
    
    def post(self, request):
        logout(request)
        messages.success(request, 'Déconnexion réussie.')
        return redirect('Gamme:login')
class op_edit(LoginRequiredMixin, DetailView):
    model = MissionControle
    template_name = 'gamme/op_edit.html'
    context_object_name = 'mission'
class login(LoginView):
    template_name = 'gamme/login.html'
    redirect_authenticated_user = True
    
    def get_success_url(self):
        if self.request.user.is_op:
            messages.info(self.request, 'Vous êtes connecté en tant qu\'opérateur.')
            return reverse_lazy('Gamme:operateur_dashboard')
        return reverse_lazy('Gamme:missioncontrole_list')
class RegisterView(CreateView):
    model = User
    form_class = RegisterForm
    template_name = 'gamme/register.html'
    success_url = reverse_lazy('Gamme:login')

    def form_valid(self, form):
        messages.success(self.request, "Inscription réussie.")
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, "Erreur dans le formulaire.")
        return self.render_to_response(self.get_context_data(form=form))
class ajouter_utilisateur(LoginRequiredMixin, CreateView):
    model = User
    form_class = RegisterForm
    template_name = 'gamme/ajouter_utilisateur.html'
    success_url = reverse_lazy('Gamme:user_list')
    
    def form_valid(self, form):
        # Save the user first
        user = form.save(commit=False)
        user.set_password(form.cleaned_data['password1'])
        
        # Handle role selection - explicitly set all role fields
        role = self.request.POST.get('role')
        print(f"Selected role: {role}")  # Debug log
        
        # Reset all roles first
        user.is_op = False
        user.is_rs = False
        user.is_ro = False
        
        # Set the selected role
        if role == 'op':
            user.is_op = True
            print("Setting role to Opérateur")  # Debug log
        elif role == 'rs':
            user.is_rs = True
            print("Setting role to Responsable")  # Debug log
        elif role == 'ro':
            user.is_ro = True
            print("Setting role to Responsable Opérationnel")  # Debug log
            
        user.save()
        print(f"User saved with is_op={user.is_op}, is_rs={user.is_rs}, is_ro={user.is_ro}")  # Debug log
        
        messages.success(self.request, "L'utilisateur a été créé avec succès.")
        return redirect('Gamme:user_list')
        
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['initial']['is_op'] = False
        kwargs['initial']['is_rs'] = False
        return kwargs



def view_gamme_pdf(request, mission_id):
    """View to display the gamme PDF for a specific mission."""
    mission = get_object_or_404(MissionControle, id=mission_id)
    
    # Get the most recent gamme for this mission
    gamme = mission.gammes.order_by('-date_creation').first()
    
    # Get operations for the most recent gamme, ordered by 'ordre'
    operations_list = []
    if gamme:
        operations_list = list(gamme.operationcontrole_set.all().order_by('ordre'))
    
    operations_dict = {}
    for i in range(1, 9): # Operations 1 to 8
        if i <= len(operations_list):
            op = operations_list[i-1]
            operations_dict[i] = {
                'description': op.description,
                'photos': op.photooperation_set.all()
            }
        else:
            operations_dict[i] = {
                'description': '',
                'photos': []
            }
    
    # Get the RS user (Responsable de Service)
    rs_user = User.objects.filter(is_rs=True).first()
    if not rs_user:
        rs_user = None
    # Get the RO user (Responsable Opérationnel)
    ro_user = User.objects.filter(is_ro=True).first()
    if not ro_user:
        ro_user = None
    
    # Ensure we have default values
    if rs_user is None:
        rs_user = request.user if request.user.is_authenticated else None
    if ro_user is None:
        ro_user = request.user if request.user.is_authenticated else None
    
    # Get PhotoDefaut objects for this gamme
    photo_defauts = []
    if gamme and hasattr(gamme, 'photodefaut_set'):
        photo_defauts = gamme.photodefaut_set.all().order_by('date_ajout')
    
    context = {
        'mission': mission,
        'gammecontrole': gamme,  # Add gamme object as gammecontrole for the template
        'operations': operations_dict,
        'title': f'Gamme - {mission.intitule}',
        'rs_user': rs_user,
        'ro_user': ro_user,
        'photo_defauts': photo_defauts,
        'static_defect_photos': [
            {'image_path': '1.jpg', 'title': 'Défaut de surface'},
            {'image_path': '2.jpg', 'title': 'Défaut d\'assemblage'},
            {'image_path': 'logo.jpg', 'title': 'Défaut de marquage'},
        ]
    }
    
    # Render the HTML view with jsPDF for client-side PDF generation
    return render(request, 'gamme/gamme_pdf.html', context)


import logging
logger = logging.getLogger(__name__)


@csrf_exempt
def save_mission_pdf(request, mission_id):
    """View to save an uploaded PDF file to the MissionControle model.
    
    This view expects a POST request with a file in the 'pdf_file' field.
    The file should be a PDF generated client-side using jsPDF.
    """
    logger.info(f"=== SAVE MISSION PDF REQUEST ===")
    logger.info(f"URL: {request.path}")
    logger.info(f"Method: {request.method}")
    logger.info(f"Content-Type: {request.content_type}")
    
    # Only allow POST requests
    if request.method != 'POST':
        logger.error(f"Method {request.method} not allowed for this endpoint")
        return JsonResponse(
            {'success': False, 'error': f'Method {request.method} not allowed'}, 
            status=405,
            headers={'Allow': 'POST'}
        )
    
    # Check if the request is multipart/form-data
    if not request.content_type.startswith('multipart/form-data'):
        logger.error(f"Invalid content type: {request.content_type}")
        return JsonResponse(
            {'success': False, 'error': 'Content-Type must be multipart/form-data'},
            status=400
        )
    
    # Check if file was uploaded
    if 'pdf_file' not in request.FILES:
        logger.error("No file part in the request")
        return JsonResponse(
            {'success': False, 'error': 'No file part'},
            status=400
        )
    
    try:
        # Get the mission object
        mission = get_object_or_404(MissionControle, id=mission_id)
        logger.info(f"Processing mission: {mission.id} - {mission.intitule}")
        
        # Get the uploaded file
        pdf_file = request.FILES['pdf_file']
        logger.info(f"Received file: {pdf_file.name}, size: {pdf_file.size} bytes, content_type: {pdf_file.content_type}")
        
        # Validate file type
        if not pdf_file.name.lower().endswith('.pdf') or 'pdf' not in pdf_file.content_type.lower():
            logger.error(f"Invalid file type: {pdf_file.content_type}")
            return JsonResponse(
                {'success': False, 'error': 'File must be a PDF'},
                status=400
            )
        
        # Delete old file if exists
        if mission.pdf_file:
            try:
                mission.pdf_file.delete(save=False)
                logger.info("Deleted old PDF file")
            except Exception as e:
                logger.warning(f"Could not delete old file: {str(e)}")
        
        # Save the new file
        file_name = f'mission_{mission.id}_gamme.pdf'
        mission.pdf_file.save(file_name, pdf_file, save=True)
        
        logger.info(f"Successfully saved PDF to {mission.pdf_file.path}")
        
        return JsonResponse({
            'success': True,
            'message': 'PDF uploaded and saved successfully',
            'pdf_url': request.build_absolute_uri(mission.pdf_file.url)
        })
        
    except Exception as e:
        logger.error(f"Error saving PDF: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

