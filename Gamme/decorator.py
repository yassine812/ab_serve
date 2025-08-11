from django.shortcuts import redirect
from django.contrib import messages
from django.http import HttpResponseForbidden

def role_required(allowed_roles):
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return HttpResponseForbidden("Vous devez être connecté pour accéder à cette page.")
            
            try:
                user = request.user
                if 'admin' in allowed_roles and user.is_superuser:
                    return view_func(request, *args, **kwargs)
                
                if 'operateur' in allowed_roles and hasattr(user, 'is_op') and user.is_op:
                    return view_func(request, *args, **kwargs)
                
                if 'responsable' in allowed_roles and hasattr(user, 'is_rs') and user.is_rs:
                    return view_func(request, *args, **kwargs)
                
                messages.error(request, "Vous n'avez pas les droits nécessaires.")
                return HttpResponseForbidden("Accès refusé.")
            except Exception as e:
                print(f"Erreur dans role_required: {str(e)}")
                return HttpResponseForbidden("Erreur lors de la vérification des droits.")
        return wrapper
    return decorator