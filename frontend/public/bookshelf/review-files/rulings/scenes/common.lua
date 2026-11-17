-- Assessment-owned scenarios. Rules themselves remain the frozen game source.
local A = {}

local function player_state(p)
  return { id=p.id, general=p.general, hp=p.hp, max_hp=p.maxHp, chained=p.chained,
    hand=table.map(p:getCardIds("h"), function(id) local c=Fk:getCardById(id); return {name=c.name,suit=c.suit,number=c.number,id=id} end),
    equip=table.map(p:getCardIds("e"), function(id) local c=Fk:getCardById(id); return {name=c.name,id=id} end) }
end

function A.start(id)
  local room = FkTest.room
  A.trace = {scene_id=id, scope="fixed-snapshot Lua rules / fake_backend", assertions={}, events={}, actions={},
    initial_players=table.map(room.players, player_state)}
  local original = room.logic.trigger
  room.logic.trigger = function(self,event,target,data,...)
    local row = {event=event.name or tostring(event), target=target and target.id, before_hp=target and target.hp}
    if type(data)=="table" then
      row.card = data.card and data.card.name
      row.damage_before = data.damage
      row.chain = data.chain
    end
    table.insert(A.trace.events,row)
    local ret = table.pack(original(self,event,target,data,...))
    row.after_hp = target and target.hp
    if type(data)=="table" then row.damage_after=data.damage end
    return table.unpack(ret,1,ret.n)
  end
  return room, room.players[1], room.players[2], room.players[3]
end

function A.actor(p, general, skills)
  local room = FkTest.room
  FkTest.runInRoom(function()
    room:prepareGeneral(p,general)
    local def=Fk.generals[general]
    room:setPlayerProperty(p,"maxHp",def.maxHp)
    room:setPlayerProperty(p,"hp",def.hp)
    if skills then room:handleAddLoseSkills(p,skills) end
  end)
end

function A.equip(p,name,suit,number)
  local room=FkTest.room
  local card=room:printCard(name,suit or Card.Spade,number or 1)
  FkTest.runInRoom(function() room:useCard{from=p,tos={p},card=card} end)
  table.insert(A.trace.actions,{action="equip",player=p.id,card=name})
  return card
end

function A.give(p,name,suit,number)
  local room=FkTest.room
  local card=room:printCard(name,suit or Card.Heart,number or 7)
  FkTest.runInRoom(function() room:obtainCard(p,card) end)
  return card
end

function A.chain(...)
  local players={...}
  FkTest.runInRoom(function() for _,p in ipairs(players) do p:setChainState(true) end end)
end

function A.eq(actual,expected,label)
  lu.assertEquals(actual,expected,label)
  table.insert(A.trace.assertions,{label=label,actual=actual,expected=expected,passed=true})
end

function A.finish(summary)
  local room=FkTest.room
  A.trace.final_players=table.map(room.players,player_state)
  A.trace.summary=summary
  A.trace.passed=true
  local file=assert(__io.open("assessment_trace_"..A.trace.scene_id..".json","w"))
  file:write(json.encode(A.trace)); file:close()
end

function A.register(id,fn)
  local name="assessment_"..id
  _G["Test"..name]=setmetatable({testScenario=function()
    A.start(id)
    local players=FkTest.room.players
    local ok,err=xpcall(function() fn(FkTest.room,table.unpack(players)) end,debug.traceback)
    if not ok then
      A.trace.passed=false
      A.trace.error=tostring(err)
      local file=assert(__io.open("assessment_trace_"..id..".json","w"))
      file:write(json.encode(A.trace)); file:close()
      error(err)
    end
  end},{__index={setup=FkTest.initRoom,tearDown=FkTest.clearRoom}})
  return {name=name}
end

return A
