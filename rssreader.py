import PySimpleGUI as sg
# Assuming t is your PySimpleGUI element, t.Widget should give you access
# to the underlying Tkinter widget.
# https://riptutorial.com/tkinter/example/31885/customize-a-treeview

folder_icon = b'iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAACXBIWXMAAAsSAAALEgHS3X78AAABnUlEQVQ4y8WSv2rUQRSFv7vZgJFFsQg2EkWb4AvEJ8hqKVilSmFn3iNvIAp21oIW9haihBRKiqwElMVsIJjNrprsOr/5dyzml3UhEQIWHhjmcpn7zblw4B9lJ8Xag9mlmQb3AJzX3tOX8Tngzg349q7t5xcfzpKGhOFHnjx+9qLTzW8wsmFTL2Gzk7Y2O/k9kCbtwUZbV+Zvo8Md3PALrjoiqsKSR9ljpAJpwOsNtlfXfRvoNU8Arr/NsVo0ry5z4dZN5hoGqEzYDChBOoKwS/vSq0XW3y5NAI/uN1cvLqzQur4MCpBGEEd1PQDfQ74HYR+LfeQOAOYAmgAmbly+dgfid5CHPIKqC74L8RDyGPIYy7+QQjFWa7ICsQ8SpB/IfcJSDVMAJUwJkYDMNOEPIBxA/gnuMyYPijXAI3lMse7FGnIKsIuqrxgRSeXOoYZUCI8pIKW/OHA7kD2YYcpAKgM5ABXk4qSsdJaDOMCsgTIYAlL5TQFTyUIZDmev0N/bnwqnylEBQS45UKnHx/lUlFvA3fo+jwR8ALb47/oNma38cuqiJ9AAAAAASUVORK5CYII='

def generate_tree_data():
    maintree = sg.TreeData()

    maintree.insert("", 1, 'Folder 1', '', icon=folder_icon)
    maintree.insert(1, 2, 'Item 1', '')
    maintree.insert(1, 3, 'Item 2', '')
    maintree.insert(1, 4, 'Item 3', '')

    maintree.insert("", 5, 'Folder 2', '', icon=folder_icon)
    maintree.insert(5, 5, 'Item 5', '')
    maintree.insert(5, 5, 'Item 6', '')
    maintree.insert(5, 5, 'Item 7', '')

    return maintree

def layout_window():
    # DarkBlue 8, 12, 13
    # DarkGrey 6, 8, 10, 11,
    sg.theme('DarkGrey11')

    treedata = generate_tree_data()

    layout = [[sg.Button('Check', key='btn_check')],
    [sg.Tree(data=treedata,headings=[ ],
                    num_rows=20,
                    col0_width=20,
                    key='maintree',
                    tooltip='blah',
                    show_expanded=True,
                    enable_events=True)]
              ]
    window = sg.Window('RSS Reader', layout, size=(600, 400), resizable=True)

    return window

def recolour_tree_item(window):
    colors = [('white', 'blue'), ('white', 'green'), ('blue', 'red')]
    index = 0
    '''
    iid = 14
    table.tag_configure(iid+1, background=colors[index][1], foreground=colors[index][0])
    index = (index+1)%3
    window['maintree'].Widget.insert('folder1', tags = ('odd',))
    window['maintree'].Widget.tag_configure('odd', background='#E8E8E8')
    window['-TABLE-'].update(cur_table, row_colors=[[j, sg.DEFAULT_BACKGROUND_COLOR, 'red'] for j in range(len(cur_table))])
    table.tag_configure("RED", foreground='red')
    '''
    tree = window['maintree'].Widget
    tree.tag_configure(1, background='white', foreground='red')

def process_events(window, event, values):
    if event == 'btn_check':
        recolour_tree_item(window)

def main():
    window = layout_window()
    generate_tree_data()

    while True:
        event, values = window.Read()
        #print(event, values)
        if event is None or event == 'Exit' or event == sg.WIN_CLOSED:
            break
        elif event == '__TIMEOUT__':
            pass
        else:
            process_events(window, event, values)

if __name__ == '__main__':
    main()
