from django import forms
from .models import Project

class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Project Name', 'class': 'form-control'}),
            'description': forms.Textarea(attrs={'placeholder': 'Describe your software idea in natural language...', 'class': 'form-control', 'rows': 5}),
        }
