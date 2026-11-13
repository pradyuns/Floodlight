-- Opens Spotlight, types a query, waits, then prints every Accessibility element in its window
-- (depth, role, subrole, description, value, identifier, selected). Exploration aid for Task 4.
on run argv
	set q to item 1 of argv
	tell application "System Events"
		key code 49 using command down
		delay 1.0
		tell process "Spotlight"
			if (count of windows) = 0 then return "no Spotlight window"
			keystroke q
			delay 2.5
			set out to ""
			set els to entire contents of window 1
			repeat with e in els
				set line_ to ""
				try
					set line_ to line_ & (role of e)
				end try
				try
					set line_ to line_ & " | sub=" & (subrole of e)
				end try
				try
					set line_ to line_ & " | desc=" & (description of e)
				end try
				try
					set v to value of e
					if v is not missing value then set line_ to line_ & " | val=" & (v as text)
				end try
				try
					set line_ to line_ & " | id=" & (value of attribute "AXIdentifier" of e)
				end try
				try
					set line_ to line_ & " | sel=" & (value of attribute "AXSelected" of e)
				end try
				try
					set line_ to line_ & " | help=" & (help of e)
				end try
				set out to out & line_ & linefeed
			end repeat
		end tell
		key code 53
	end tell
	return out
end run
