from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib import messages


def login_view(request):
    """Custom login view — renders combined sliding auth panel."""
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            next_url = request.GET.get('next', '')
            return redirect(next_url if next_url else 'dashboard')
    else:
        form = AuthenticationForm()

    return render(request, 'authentication/login.html', {
        'form': form,
        'reg_form': UserCreationForm(),
        'initial_panel': 'login',
    })


def register_view(request):
    """Registration view — same sliding panel, pre-slid to register side."""
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Registration successful. Welcome!")
            return redirect('dashboard')
        # form errors display inline — no separate flash needed
    else:
        form = UserCreationForm()

    return render(request, 'authentication/register.html', {
        'form': AuthenticationForm(),
        'reg_form': form,
        'initial_panel': 'register',
    })
