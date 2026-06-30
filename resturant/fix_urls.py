import sys
with open('urls.py', 'r') as f:
    lines = f.readlines()
# Find index of the line with the order status path
for i, line in enumerate(lines):
    if 'path("kitchen/order/<int:order_id>/status/"' in line:
        # Insert after this line
        lines.insert(i+1, '    path("kitchen/table/<int:table_id>/mark-ready/", views.mark_table_orders_ready, name="mark_table_orders_ready"),\n')
        break
with open('urls.py', 'w') as f:
    f.writelines(lines)
