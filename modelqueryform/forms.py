from django.forms import Form, MultipleChoiceField
from django.db import models
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.forms.widgets import CheckboxSelectMultiple, MultiWidget, TextInput, CheckboxInput
from django.utils.safestring import mark_safe
from django.forms.fields import Field
from django.db.models.aggregates import Min, Max
from django.db.models.query_utils import Q
import operator
from collections import OrderedDict

class ModelQueryForm(Form):
    model = None
    exclude = None
    
    RANGE_TYPES = (
                     models.BigIntegerField,
                     models.DecimalField,
                     models.FloatField,
                     models.IntegerField,
                     models.PositiveIntegerField,
                     models.PositiveSmallIntegerField,
                     models.SmallIntegerField
                   )
    
    def __init__(self, *args, **kwargs):
        super(ModelQueryForm, self).__init__(*args, **kwargs)
        try:
            self.model_fields = self.model._meta.fields
        except:
            raise ImproperlyConfigured("ModelQueryForm needs a model to work with")
        
        for field in self.model_fields:
            if field.name in self.exclude:
                continue
            if isinstance(field, self.RANGE_TYPES) and field.choices == []: 
                self.fields[field.name] = RangeField(label = field.verbose_name, required = False, model = self.model, field = field.name)
            else:
                if field.choices == []:
                    choices = [(x, x) 
                                for x in 
                                  self.model.objects.distinct()
                                                    .order_by(field.name)
                                                    .values_list(field.name, flat=True)
                              ]
                else:
                    choices = field.choices
                self.fields[field.name] = MultipleChoiceField(label = field.verbose_name, required = False, widget = CheckboxSelectMultiple, choices = choices)
    
    def clean(self):
        cleaned_data = super(ModelQueryForm, self).clean()
        
        return cleaned_data
    
    def process_model_query(self, data_set = None):
        if not data_set:
            data_set = self.model.objects.all()
        
        try:
            data_set.exists()
        except:
            raise ImproperlyConfigured("Model query requires a QuerySet to filter against")
        
        for field in self.changed_data:
            values = self.cleaned_data[field]
            query_list = []
            if not isinstance(values, dict):
                for value in values:
                    query_list.append(Q(**{field: value}))
            else:
                if values['allow_empty']:
                    query_list.append(Q(**{field: None}))
                range_min = values['min']
                range_max = values['max']
                if range_min == range_max:
                    query_list.append(Q(**{field: range_min}))
                else:
                    range_list = []
                    range_list.append(Q(**{field + '__gte': range_min}))
                    range_list.append(Q(**{field + '__lte': range_max}))
                    
                    query_list.append(reduce(operator.and_, range_list))
            
            data_set = data_set.filter(reduce(operator.or_, query_list))
            
        return data_set
    
    def get_vals_for_pretty_print(self):
        vals = OrderedDict()
        for field in self.fields:
            try:
                if self.initial[field]:
                    try:
                        choices = self.fields[field].choices
                        for selected in self.initial[field]:
                            try:
                                vals[self.fields[field].label]
                                vals[self.fields[field].label] = "%s; %s" % (vals[self.fields[field].label],dict(choices)[int(selected)])
                            except:
                                vals[self.fields[field].label] = "%s" % dict(choices)[int(selected)]                                
                    except:
                        vals[self.fields[field].label] = "%s - %s" %(self.initial[field][0], self.initial[field][1])
                        if len(self.initial[field]) == 3:
                            vals[self.fields[field].label] = "%s. %s" %(vals[self.fields[field].label], "Includes Empty Values")
            except:
                pass
            
        return vals
    
class RangeWidget(MultiWidget):
    def __init__(self, attrs = None, mode = 0):
        _widgets = (
            TextInput(attrs = attrs),
            TextInput(attrs = attrs),
            CheckboxInput()
        )
        super(RangeWidget, self).__init__(_widgets, attrs)

    def decompress(self, value):
        if value:
            return [value['min'], value['max'], value['allow_empty']]
        return [None, None]

    def value_from_datadict(self, data, files, name):
        value = {}
        try:
            if not data[name + "_0"] == '':
                value['min'] = data[name + "_0"]
                value['max'] = data[name + "_1"]
                try:
                    if data[name + "_2"]:
                        value['allow_empty'] = True
                except:
                    value['allow_empty'] = False
        except:
            pass
        return value
    
    def format_output(self, rendered_widgets):   
        return mark_safe(u'%s %s<br/> %s %s' % \
            (rendered_widgets[0], rendered_widgets[1], 'Allow Empty Values', rendered_widgets[2]))

class RangeField(Field):
    def __init__(self, model, field, *args, **kwargs):
        range_min = model.objects.all().aggregate(Min(field))[field + "__min"]
        range_max = model.objects.all().aggregate(Max(field))[field + "__max"]
        super(RangeField, self).__init__(*args, **kwargs)
        self.widget = RangeWidget({'min':range_min, 'max':range_max})
        
    def to_python(self, value):
        if not value:
            return []
        try:
            value['allow_empty'] = value['allow_empty']
            value['min'] = int(value['min'])
            value['max'] = int(value['max'])
        except:
            try:
                value['min'] = float(value['min'])
                value['max'] = float(value['max'])                
            except:
                raise ValidationError('Values in RangeField must be numeric')
            
        return value
    
    def validate(self, value):
        if value:
            if value['min'] > value['max']:
                raise ValidationError('Min must be less than or equal to Max')
