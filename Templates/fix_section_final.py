import re

with open('kitchendashboard.html', 'r') as f:
    content = f.read()

start_marker = '<h2 class="font-headline-md text-headline-md text-on-surface mb-6">Live Tickets</h2>'
start = content.find(start_marker)
if start == -1:
    print("Start marker not found")
    exit(1)

end = content.find('</section>', start)
if end == -1:
    print("End section not found")
    exit(1)
end += len('</section>')

new_section = '''<h2 class="font-headline-md text-headline-md text-on-surface mb-6">Live Tickets</h2>
{% regroup orders by table_session.table as table_group %}
<div class="grid grid-cols-1 lg:grid-cols-3 gap-gutter">
{% for table in table_group %}
<div class="bg-surface-container p-6 rounded-2xl border-2 border-outline-variant">
<div class="flex justify-between items-center mb-4">
    <h3 class="font-headline-md text-headline-md">Table {{ table.grouper.number }}</h3>
</div>
{% for order in table.list %}
<div class="bg-surface-container p-4 rounded-xl border-2 mb-4 {% if order.status == 'pending' %}border-error ticket-urgent{% else %}border-outline-variant{% endif %}">
<div class="flex justify-between items-center mb-2">
<span class="font-body-md text-on-surface">Order #{{ order.id }}</span>
<span class="px-2 py-0.5 text-label-sm rounded-full
  {% if order.status == 'pending' %}bg-error text-white
  {% elif order.status == 'preparing' %}bg-primary text-on-primary
  {% elif order.status == 'ready' %}bg-primary-container text-on-primary-container
  {% endif %}">{{ order.get_status_display }}</span>
</div>
<ul class="space-y-1 mb-2">
{% for line in order.items.all %}
<li class="flex justify-between text-body-sm">
<span>{{ line.quantity }}x {{ line.menu_item.name }}</span>
</li>
{% endfor %}
</ul>
<p class="text-on-surface-variant text-label-sm mb-2">Placed {{ order.placed_at|timesince }} ago</p>
<form action="{% url 'advance_order_status' order_id=order.id %}" method="post" class="pt-2 border-t border-outline-variant">
{% csrf_token %}
{% if order.status == 'pending' %}
<button type="submit" name="status" value="preparing" class="w-full bg-primary text-on-primary font-bold py-1 rounded-xl">Start preparing</button>
{% elif order.status == 'preparing' %}
<button type="submit" name="status" value="ready" class="w-full bg-primary-container text-on-primary-container font-bold py-1 rounded-xl">Finished Preparing</button>
{% elif order.status == 'ready' %}
<button type="submit" name="status" value="served" class="w-full bg-surface-container-high text-on-surface font-bold py-1 rounded-xl">Mark served</button>
{% endif %}
</form>
</div>
{% empty %}
<p class="text-on-surface-variant text-center py-4">No orders for this table.</p>
{% endfor %}
</div>
{% empty %}
<p class="text-on-surface-variant col-span-full text-center py-12">No live tickets right now.</p>
{% endfor %}
</div>
</section>'''

new_content = content[:start] + new_section + content[end:]

with open('kitchendashboard.html', 'w') as f:
    f.write(new_content)
print('Replaced successfully')
