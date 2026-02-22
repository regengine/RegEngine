import re

with open('src/components/layout/header.tsx', 'r') as f:
    content = f.read()

# Pattern to find all vertical links inside the Industry Frameworks DropdownMenuContent
start_marker = '<DropdownMenuLabel className="text-xs uppercase text-muted-foreground tracking-wider">Industry Frameworks</DropdownMenuLabel>'
end_marker = '</DropdownMenuContent>'

start_idx = content.find(start_marker)
end_idx = content.find(end_marker, start_idx)

dropdown_content = content[start_idx:end_idx]

# Split by DropdownMenuItem
items = dropdown_content.split('<DropdownMenuItem asChild>')
new_dropdown_content = items[0]

for item in items[1:]:
    # Is it food safety?
    if 'href="/verticals/food-safety"' in item:
        new_dropdown_content += '<DropdownMenuItem asChild>' + item
    else:
        # It's an inactive vertical
        # Replace <Link ...> with <div ... opacity-50 cursor-not-allowed> and add Soon badge
        item_mod = re.sub(r'<Link href="[^"]+" className="cursor-pointer w-full flex items-center gap-3 py-2">',
                          '<div className="w-full flex items-center gap-3 py-2 opacity-50 cursor-not-allowed">', item)
        item_mod = item_mod.replace('</Link>', '</div>')
        # Add Soon badge next to font-medium
        item_mod = re.sub(r'(<div className="font-medium">)([^<]+)(</div>)',
                          r'\1\2 <span className="text-[9px] uppercase font-bold text-muted-foreground ml-1 ring-1 ring-muted px-1 rounded">Soon</span>\3', item_mod)
        new_dropdown_content += '<DropdownMenuItem disabled>' + item_mod

content = content[:start_idx] + new_dropdown_content + content[end_idx:]

with open('src/components/layout/header.tsx', 'w') as f:
    f.write(content)
print("Updated header.tsx")
