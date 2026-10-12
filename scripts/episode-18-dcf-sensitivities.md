# The Deal Desk, episode 18: D-C-F sensitivities and traps, or the shares that were counted twice
A four billion dollar software takeover went through at twenty-four dollars a share. With the right share count, the same money was worth fifty-eight cents more.

---

MARCO: This is The Deal Desk, episode eighteen. Episode sixteen set the discount rate, episode seventeen the terminal value. Today, what happens when you move them, and the mistakes that make a model lie. And we start not in a courtroom, but in a spreadsheet.

SOFIA: Whose spreadsheet?

MARCO: In September twenty fourteen, Vista Equity Partners, a private equity firm, agreed to buy Tibco, an American software company, for twenty-four dollars a share in cash. The announcement put the enterprise value at about four point three billion dollars.

SOFIA: Sounds like a normal deal.

MARCO: It was, for about a week. Then someone at Goldman Sachs, Tibco's adviser, looked at the total and wrote that it didn't look right. The capitalisation table, the list of every share the company had, counted about four point one million unvested restricted shares twice. Those are shares promised to staff that they haven't fully earned yet.

SOFIA: Four million out of how many?

MARCO: About a hundred and seventy-three million. A little over two percent. But Vista later said it had relied on that same table for its final bid. The deal had been presented as equity worth about four point two four billion dollars. At twenty-four dollars, with the right count, it was only about four point one four billion. Pay the bigger total over the right number of shares, and you get about twenty-four dollars fifty-eight.

SOFIA: So shareholders missed fifty-eight cents a share.

MARCO: About a hundred million dollars in total. Tibco's board went ahead at twenty-four dollars and never asked Vista to pay the difference. Shareholders sued, and in September twenty sixteen a Delaware court approved a thirty million dollar settlement.

SOFIA: Nobody got the growth rate wrong. Nobody argued about the discount rate.

MARCO: A share count. By the end of today you'll know both ways a D-C-F misleads you: the assumptions that swing it, and the plain mistakes nobody checks.

SOFIA: Start with the assumptions, then. Last time Cafe Group came out at about one thousand three hundred and forty. That's the answer?

MARCO: That's one answer. It rests on two numbers we chose: a nine percent discount rate and two percent growth. First trap: presenting a D-C-F as a single number. Nobody in a bank does that. You build a sensitivity table. Discount rate down the side, eight, nine and ten percent. Long-term growth across the top, one, two and three percent. Nine cells, nine values.

SOFIA: And they'll all be close to one thousand three hundred and forty.

MARCO: Let's see. Keep the five forecast years at one hundred of cash each, which is what gives just under four hundred in today's money. The middle cell, nine and two, is our one thousand three hundred and forty. Now one point cheaper money and one point more growth, eight and three: about one thousand eight hundred. The opposite corner, ten and one: about one thousand and eighty.

SOFIA: From one thousand and eighty to one thousand eight hundred. Same company.

MARCO: Same five years of cash. Everything else is two assumptions. And look at the shape. The low corner is about a fifth below the middle. The high corner is about a third above it.

SOFIA: Why isn't it symmetric?

MARCO: Because the gap between the discount rate and the growth rate sits at the bottom of a fraction. In the middle cell the gap is seven points. Shrink it to five and the value jumps. Widen it to nine and the value falls, but by less. So in a D-C-F, optimism moves the answer more than pessimism does.

SOFIA: Then I'll use wide ranges, to be safe. Growth from zero all the way to six percent.

MARCO: Second trap. A range that wide isn't caution, it's saying nothing. At six percent growth and an eight percent discount rate the gap is two points, and the value tops four thousand, three times the middle. Flex each input by what you could honestly defend: half a point to a point on the discount rate, half a point on growth. If the corners of your table run from cheap to absurd, the table hasn't helped anyone.

SOFIA: Okay. And if I want more growth in the forecast, I just raise the growth rate?

MARCO: Third trap. Growth isn't free. To grow faster, Cafe Group has to open cafés, buy ovens and carry more stock. Raise growth and leave capex where it was, and you've given the company the growth without making it pay for it. Good models link the two: more growth, more reinvestment, less free cash flow in the early years.

SOFIA: Episode fifteen again.

MARCO: Always. Fourth trap, and it's the Tibco trap: the walk from enterprise value to a share price. Say Cafe Group's numbers are in millions of euros. Enterprise value, one thousand three hundred and forty million. One hundred million shares. What's a share worth?

SOFIA: Thirteen euros forty.

MARCO: That's the whole business, including the part that belongs to lenders. First subtract net debt, say three hundred and forty million. Equity value: one billion euros. Ten euros a share.

SOFIA: Ten euros, then.

MARCO: Not yet. Staff hold options and restricted shares. Say they add up to five million more shares once you count them properly. Divide one billion by one hundred and five million: about nine euros fifty. That's the diluted share count, and it's exactly where Tibco went wrong. Count shares twice, and the buyer pays less per share for the same total.

SOFIA: So the most expensive mistake in the story wasn't in the D-C-F at all.

MARCO: The most common ones usually aren't. They're in the plumbing. A share count. Net debt that leaves out leases. Cash flows in dollars discounted at a rate built for euros. And the hockey stick: years of flat sales, then growth that takes off the year after the deal. Check the forecast against the company's own history and its peers.

SOFIA: Okay.

MARCO: What they'll ask you. First: you've built a D-C-F. How do you present the result?

SOFIA: I give the enterprise value and the share price it implies.

MARCO: That's one number, and they'll ask how sure you are. The strong answer: a range. Show a sensitivity table on the discount rate and the long-term growth rate, or the exit multiple if you used one. Say which assumption moves the value most. Then put the range on the football field next to comparable companies and precedent transactions, and explain where they agree and why they don't.

SOFIA: Second?

MARCO: Your D-C-F gives an enterprise value of one billion. Net debt is two hundred million. There are forty million basic shares, plus staff options. What's a share worth?

SOFIA: One billion divided by forty million. Twenty-five.

MARCO: Two mistakes. Enterprise value belongs to lenders and shareholders together, so subtract the net debt first: eight hundred million of equity. Then divide by the diluted count, not the basic one. Bankers count the options that are in the money with the treasury stock method, which we'll do properly in a later episode. So the answer is below twenty, by however much the options dilute it.

SOFIA: Third?

MARCO: What's the biggest weakness of a D-C-F?

SOFIA: It's all assumptions, so you can make it say anything. It's not very useful.

MARCO: Half right. It's sensitive, mostly through the terminal value, and a model can be bent to any answer. But that's also its strength: every assumption is written down where someone can challenge it. So say both, then say how you'd handle it: a sensitivity table, and a check against the market.

SOFIA: Deal of the day?

MARCO: A Swedish buyer and a software target, like Tibco. On Friday, the ninth of October, Hexagon, the Swedish measurement and sensor group, agreed to buy Rocscience, a Canadian software company. Rocscience helps engineers model how rock and soil behave: whether a slope will hold in a mine, how a tunnel or a dam will perform over time.

SOFIA: Who's selling?

MARCO: TA Associates, the private equity firm, which became Rocscience's first institutional investor in June twenty twenty-three, along with the founders and management. The company was founded in nineteen ninety-six at the University of Toronto. Enterprise value: about five hundred and thirty-five million dollars, on a cash-free, debt-free basis.

SOFIA: And how big is it?

MARCO: Hexagon expects revenue approaching fifty million dollars in twenty twenty-six, with more than eighty percent of it recurring. And margins above forty percent on Hexagon's own measure of operating profit. The deal should add to Hexagon's net income from closing, due in the fourth quarter of twenty twenty-six.

SOFIA: Five hundred and thirty-five million for fifty million of revenue. That's more than ten times revenue.

MARCO: And forty percent of fifty million is about twenty million dollars of profit, so roughly twenty-five times that. Hexagon's reason is a fit: its radar sensors measure how the ground moves, and Rocscience's models predict how it should move. So here's your interview question. You're asked whether Hexagon paid a sensible price. How do you use a D-C-F?

SOFIA: I build a D-C-F of Rocscience. If it comes out below five hundred and thirty-five million, Hexagon overpaid.

MARCO: That's the first trap again: one model, one number, and a verdict. The strong answer runs the model backwards. That's a reverse D-C-F: start from the price and work out what growth and margins it requires, then judge whether those are believable. And flex revenue growth and margin, not only the discount rate and terminal growth, because for a young software company they drive the value. Finally, part of the price pays for the fit with Hexagon's sensors, so Rocscience on its own should come out below what Hexagon paid. That gap is what Hexagon has to deliver.

SOFIA: So the price is a set of assumptions too. You just have to find them.

MARCO: Nicely put. Quiz. For you listening. Question one: a D-C-F gives an enterprise value of eight hundred million, net debt is two hundred million, and there are forty million basic shares and fifty million diluted shares. What's a share worth? Question two: in a sensitivity table, why does the high corner sit further from the middle than the low corner? Question three: you raise the growth rate in your forecast and leave capex unchanged. What's wrong? Question four: what went wrong in Tibco's sale to Vista? Question five: what is a reverse D-C-F?

MARCO: Pause here if you want to think it through.

MARCO: Answers. One: twelve. Eight hundred minus two hundred is six hundred million of equity, divided by fifty million diluted shares. Two: the gap between the discount rate and the growth rate sits at the bottom of a fraction, so narrowing it raises the value faster than widening it lowers it. Three: the company gets the growth without paying for it, so the value is overstated. Four: unvested restricted shares were counted twice, so twenty-four dollars a share came to about a hundred million dollars less than the total presented. Five: starting from the price and working out what growth and margins it requires.

SOFIA: So a D-C-F is only as good as its inputs, and its share count.

MARCO: And so far we've valued the whole business, for lenders and shareholders together. Tomorrow, episode nineteen: levered versus unlevered free cash flow. What changes when you value only the shareholders' slice, and the discount rate that has to change with it.
