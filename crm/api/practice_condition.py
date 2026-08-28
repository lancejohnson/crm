# Copyright (c) 2026, Groundwork and contributors
# For license information, please see license.txt

"""Seller-voice condition lines for practice properties.

Real phrasing from CRM call transcripts, lightly cleaned. No repair labels —
the trainee decides the rung. Pick one at property-create time.
"""

from __future__ import annotations

import random

# Voices, not buckets. Enough variety that two houses in a set rarely rhyme.
SELLER_NOTES: tuple[str, ...] = (
	"Of course it needs a lot of work. It's in good condition because I live there. But you know, it's an old house. Let's face it — it's almost a hundred years old.",
	"I'd say it's in good condition. They've never complained or called me. They usually just repair whatever they need and move on. And I don't go into the property, so I couldn't really tell you a whole lot what's going on.",
	"I live there. I'm the only one that lives there. It could be a new kitchen. It depends on how you like your bathroom, but the bathrooms are in good shape, all of them.",
	"Plumbing works, electrical, air conditioning, everything working fine. You know, people live there.",
	"It's in good condition. The third floor has a leak in the roof right now — just that roof is gonna need to be fixed. It's in use-of condition because I use it. It's not a new renovated kitchen.",
	"You can say cosmetic repair. The roof, it's been a while. It's probably twenty years since they changed it. They are old, but they're working fine.",
	"My roof don't leak even though it's outlived it — it's twenty years. The insurance company is gonna say you need a roof. What I wanna sell it as is.",
	"The windows are fine. There's nothing wrong with them. The crawl space under the bathroom is kinda bowed out, but no water gets in there. But it does need a new furnace, air conditioner, and hot water heater.",
	"I'm not really quite sure, but I do know it doesn't leak. It's been a long time since the kitchen and bath were updated. There is some bowing in one wall underneath the crawl space.",
	"The basement does not leak as long as you keep the gutters cleaned out and away from the house.",
	"It's just cosmetics, bro. I can do it myself. Actually, that would be one of the main things, the kitchen and the bathroom. The bathroom's not terrible, and the kitchen's not either. I've painted it many times, but the kitchen could use some facing.",
	"Kitchen and bath needs remodeled, and the inside is cosmetic, man. It just needs some paint. Kitchen needs to be done, and bathroom needs to be redone.",
	"It's gonna need remodeling of the kitchen. Probably the bathroom. It does need work, cosmetics. The outside probably needs painting. Could be a roof — we had one put on in 2003. Furnace too.",
	"It's cosmetic stuff. There's nothing major. The roof is less than ten years. The air conditioner is less than ten years. We just painted and we put LVT floors in. A squirrel had a hole through the fascia, but it's not like the roof was rotted.",
	"The biggest thing it needs is just freshened up outside. It's pretty much all carpeted except for the kitchen and the dining room. I've been the only one here since. So everything's pretty good shape.",
	"If somebody wishes to upgrade, they can, but the house doesn't need it. There's a $20,000 roof from three years ago, new AC last March, doors and paint are fine. Everything's original in the house.",
	"It doesn't need any work. You can actually use it. It was just my color preference — changing the color tile. It needs painting, new colors and all. But nothing's in replacement condition.",
	"If you wanted to update it, those things need to be updated.",
	"Well, it needs a lot of work. The bathroom needs to be gutted. All the floors need to be redone. The basement needs to be done again. Kitchen could use new flooring, new appliances. AC went out last year.",
	"I redid the entire kitchen in 2011. Little drywall repairs, paint, stuff like that. Plan on replacing all the appliances — they're about 15 years old. Other than that, yeah, it's move-in ready.",
	"Got a new roof, new paint, three bedroom, two bath, fireplace, two car garage, big yard, and everything is good to go. The house is under good condition.",
	"Anything else that you repair, you're repairing it because you wanna paint the walls or you wanna put carpet in or you wanna change the bathroom. Everything else works.",
	"I'm not gonna try and fix it up. It's gonna need a full gut job. It's got a boiler furnace in there. Electrical needs to be updated. It's gonna need a roof. But the bricks are good on it.",
	"I've taken care of it and replaced the furnace when it was required, the air condition when it was required, the roof when it was required, and the landscaping is beautiful.",
	"When I bought it, the guys I bought it from said he has a new roof. He said that he did the roof. The foundation, not sure.",
	"It needs quite a bit. I put a new roof on it — that'll probably be about ten years ago. And it needs some major overhaul. Part of some of the walls still got the old log-cabin logs in it.",
	"The house is 80 years old, and that house needs a total repair — inside, outside, roof, heating and air — because the house is old, just like you and me.",
	"I was gonna do some rehab myself, but I don't really have time at all to focus in there.",
	"It needs a new roof, which I'm going to do before the summer's over. I'm gonna do that myself, and then it probably needs an updated kitchen. Otherwise, yeah, it's in good shape.",
	"I stripped the walls now. I ain't stripped all of them. Everything else is good. It's just the roof part. Not every room, but the plan is get that old drywall off, making sure no mold is behind.",
	"Majority of the drywall has been removed and needs flooring, drywall, paint, maybe rehab. There was a water pipe that broke, and I ripped all the drywall out because it was wet.",
	"The two bedroom carpets should need to be replaced. They're over ten years old, and I smoked, and I have a cat in the house, so it's just best to replace them. They're not destroyed destroyed. The last guy slapped on one coat of paint and put the cheapest flooring he could find.",
	"It needs some work because I had some squatters living in my house, and they kinda destroyed a few things, I guess — like the floors. They painted. I live in it now.",
	"It's down to the studs. You gotta do that and bring it up to code. That one needs a roof, AC unit. And then the rest of it, really just sheetrock work.",
	"You have to totally gut it. Looking at the way it looks, it looks like trash, except if you have a good eye and see the location. It could be torn down, but it's brick, so I wouldn't. It's a hot mess, the house.",
	"There's no kitchen in there. There's nothing in there. It's gutted out because he was gonna make apartments out of it. The structure is great, but it needs a rehab on the inside.",
	"They gutted the house all the way down to the studs. All new walls, insulation, added square footage. It's a brand new house, man.",
	"It's been vacant about seven or eight years. The roof, we're gonna probably have the roof replaced. That's why we're selling it as is. Somebody wants to purchase it, they purchase it and replace the roof.",
	"We're either going to sell it as is or we're gonna repair it depending on how much money we can get. I don't see us moving back into the house that strongly.",
	"That's good if you want to sell it as is without me putting any more money into the place. That's why I want a cash buyer.",
	"The roof is old as the house is, so I guess I don't know. A roof's gonna need to be changed. You're gonna spend anywhere from 48 to 50,000 fixing it. Like I told you, it's a Reno.",
	"They told me it was gonna be $90,000 to fix it, which I can't believe that because I do construction and carpentry a little bit. I was just gonna take the back of the house.",
	"I'd say four, five thousand, maybe. New flooring, paint job, you know, stuff like that. The new kitchen cabinets, about eight or nine years ago.",
	"I can't tell you about the inside because she's lived there eight or nine years. If you want to go look at it, make an offer, feel free. Otherwise I don't know the condition of anything inside.",
	"I haven't been there in about ten years. I don't know what it looks like. I don't know nothing about it.",
	"The last time I see it, it was in a good condition. Oh, that was five years ago.",
	"You have to look. I haven't looked into details like that.",
	"I've been in it when I bought it, but it's been vacant since. You could tear it down, and I'm concerned about anybody going inside it. The back deck is falling apart. It's not even safe walking on the deck to get into the house.",
	"There's a building on it, but it's not livable right now. It's not up to code. That's why I said it's not livable — it needs to be brought to code.",
	"It's rented right now, but it's just month to month, because I don't want it to be vacant. It needs to be painted. For updating purposes, in my opinion.",
	"So the house is in really good shape. No repairs necessary. Obviously you might need to come in, clean up, paint, do some touch painting. Other than that, everything else is completely operational.",
	"If you guys looking for a rehab or something like that, this is not it. This house is fully remodeled.",
	"It's good condition. The only thing probably needs to be fixing is the roof problem. I said everything is good. Only thing might need fixing is the roof. I'm thinking it's about fifteen years.",
	"The garage needs fixing. We got some structural damage, but that's it. The house is in perfect condition other than that. My two sons are living in the house right now.",
	"It's quite an old home. However, it was very, very good condition and good material. So the house still in good shape.",
	"My tenant is inside, but there's a nonpayment tenant. You have to buy with the tenant. Condition is not bad. Everything is active — gas — you have to do cosmetic work itself. Some painting. No leakage right now, but if you do the roof it's okay; if not, in a couple of years it's fine.",
	"I've lived here three years, and I've had a couple people come, but they all say the HVAC has to be replaced. The kitchen floor needs a little work. The bathroom needs to be updated, full bath.",
	"It's 102 years old, and it has window units for AC. The roof is metal, and it's in good condition. The foundation was redone in 2008. Tastes have changed — maybe a paint job. Twenty years ago when I painted it last.",
	"I gutted it to the studs and fixed the roof, put the joists in, re-leveled it, and I need to do the complete electrical. Bathrooms, everything was gutted. Need to put new cabinets in, new tub, new sink, new vanity.",
	"It had flooding a year and a half ago. Four feet of sheetrock. It's gonna need cabinets, air conditioning, fixtures. You'd probably come in with, I'm gonna guess, anywhere from 30 to 50 to fix it up.",
)


def pick_seller_note(used: set[str] | None = None) -> str:
	"""One line for a new practice property. Avoid repeats in the same set."""
	pool = list(SELLER_NOTES)
	if used:
		fresh = [n for n in pool if n not in used]
		if fresh:
			pool = fresh
	return random.choice(pool)
