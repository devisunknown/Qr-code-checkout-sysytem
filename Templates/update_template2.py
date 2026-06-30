import re

with open('kitchendashboard.html', 'r') as f:
    content = f.read()

pattern = r'(<div class="flex justify-between items-center mb-4">\s*)(<h3 class="font-headline-md text-headline-md">Table \{ \{ table\.grouper\.number \} \}</h3>\s*)(</div>)'

replacement = r'\1\2    <div>\n        <form action="{% url \'mark_table_orders_ready\' table.grouper.id %}" method="post" class="ml-2">\n            {% csrf_token %}\n            <button type="submit" class="bg-primary text-on-primary font-bold py-1 px-3 rounded-xl">Done Preparing</button>\n        </form>\n    </div>\n\3'

new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)

with open('kitchendashboard.html', 'w') as f:
    f.write(new_content)
print('Done')
