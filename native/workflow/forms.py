from django import forms
from .models import Artifact, Review

class ArtifactEditForm(forms.ModelForm):
    class Meta:
        model = Artifact
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={'class': 'form-control', 'rows': 20, 'style': 'font-family: monospace;'}),
        }

class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ['action', 'feedback']
        widgets = {
            'action': forms.HiddenInput(),
            'feedback': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Provide feedback (required for Reject/Regenerate)'}),
        }
