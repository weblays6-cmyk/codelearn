from django.db import migrations
from django.db.models import NOT_PROVIDED
from django.db.migrations.exceptions import IrreversibleError


class EnsureNullableUniqueField(migrations.operations.base.Operation):
    reversible = False
    reduces_to_sql = False

    def __init__(self, model_name, field_name, field):
        self.model_name = model_name
        self.field_name = field_name
        self.field = field

    def deconstruct(self):
        return (
            'blog.migration_ops.EnsureNullableUniqueField',
            [self.model_name, self.field_name, self.field],
            {},
        )

    def state_forwards(self, app_label, state):
        state.add_field(app_label, self.model_name, self.field_name, self.field, preserve_default=True)

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        model = to_state.apps.get_model(app_label, self.model_name)
        field = model._meta.get_field(self.field_name)
        table = model._meta.db_table
        with schema_editor.connection.cursor() as cursor:
            columns = {
                column.name
                for column in schema_editor.connection.introspection.get_table_description(cursor, table)
            }
            if field.column not in columns:
                schema_editor.add_field(model, field)
            else:
                constraints = schema_editor.connection.introspection.get_constraints(cursor, table)
                is_unique = any(
                    constraint['unique'] and constraint['columns'] == [field.column]
                    for constraint in constraints.values()
                )
                old_field = field.clone()
                old_field.null = False
                old_field._unique = is_unique
                old_field.default = NOT_PROVIDED
                old_field.set_attributes_from_name(field.name)
                old_field.model = model
                intermediate_field = field.clone()
                intermediate_field._unique = False
                intermediate_field.set_attributes_from_name(field.name)
                intermediate_field.model = model
                schema_editor.alter_field(model, old_field, intermediate_field, strict=False)

            quote = schema_editor.quote_name
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(
                f'UPDATE {quote(table)} SET {quote(field.column)} = NULL '
                f'WHERE TRIM({quote(field.column)}) = %s',
                [''],
            )
        if field.column in columns:
            schema_editor.alter_field(
                model,
                intermediate_field,
                field,
                strict=False,
            )

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        raise IrreversibleError('Enrollment certificate codes cannot be safely rolled back.')

    def state_backwards(self, app_label, state):
        state.remove_field(app_label, self.model_name, self.field_name)

    def describe(self):
        return f'Ensure {self.model_name}.{self.field_name} is nullable and unique'