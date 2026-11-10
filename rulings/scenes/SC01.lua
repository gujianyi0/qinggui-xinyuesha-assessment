local A=__dofile("assessment_scenes/common.lua")
return A.register("SC01",function(room,attacker,target)
  A.actor(target,"zhugeliang","kongcheng")
  A.equip(attacker,"blade")
  local jink=A.give(target,"jink",Card.Heart,2)
  local first=A.give(attacker,"slash",Card.Spade,7)
  local second=A.give(attacker,"slash",Card.Club,8)
  local before
  FkTest.runInRoom(function() before=attacker:canUseTo(second,target,{bypass_times=true,bypass_distances=true}) end)
  A.eq(before,true,"有手牌时可指定诸葛亮")
  FkTest.setNextReplies(target,{FkTest.ReplyCard(jink)})
  -- The fake backend trusts scripted replies. Do not submit a deliberately
  -- illegal target; check real target legality below, and decline this prompt.
  FkTest.setNextReplies(attacker,{"__cancel"})
  FkTest.runInRoom(function() room:useCard{from=attacker,tos={target},card=first} end)
  A.eq(target.hp,3,"第一张杀被闪抵消，空城后追杀未造成伤害")
  A.eq(target:isKongcheng(),true,"最后一张闪离手后为空城")
  local after
  FkTest.runInRoom(function() after=attacker:canUseTo(second,target,{bypass_times=true,bypass_distances=true}) end)
  A.eq(after,false,"青龙绕过次数距离，仍不绕过空城禁止指定")
  A.finish("诸葛亮打出最后一张闪后满足空城。青龙追杀不能绕过空城的目标禁止。")
end)
