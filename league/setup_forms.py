from django import forms

from .models import Event


class BasicsForm(forms.ModelForm):
    start_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    courts = forms.IntegerField(min_value=1, max_value=20)
    weeks = forms.IntegerField(min_value=1, max_value=20)

    class Meta:
        model = Event
        fields = ["name", "start_date", "courts"]

    field_order = ["name", "start_date", "weeks", "courts"]

    def __init__(self, *args, locked: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["weeks"].initial = self.instance.weeks.count() if self.instance.pk else 4
        if not self.instance.pk:
            self.fields["courts"].initial = 2
        if locked:
            for name, field in self.fields.items():
                if name != "name":
                    field.disabled = True
            self.fields["weeks"].help_text = "Scores have been entered, so the weeks can't change."


class ScoringForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ["match_format", "points_to_win", "win_by_two", "player_score_entry"]
        labels = {
            "match_format": "Match format",
            "points_to_win": "Points to win",
            "win_by_two": "Win by two",
            "player_score_entry": "Players can enter their own scores",
        }

    def __init__(self, *args, locked: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        if locked:
            for name, field in self.fields.items():
                if name != "player_score_entry":
                    field.disabled = True
