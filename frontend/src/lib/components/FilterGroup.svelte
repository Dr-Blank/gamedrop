<script>
	import { X, Plus, GitBranch, ArrowLeftRight } from '@lucide/svelte';
	import FilterGroup from './FilterGroup.svelte';

	/** @type {{ group: any, fields: any[], stores?: any[], depth?: number, onremove?: () => void }} */
	let { group = $bindable(), fields, stores = [], depth = 0, onremove } = $props();

	const OP_LABELS = {
		eq: 'is',
		ne: 'is not',
		gt: '>',
		gte: '≥',
		lt: '<',
		lte: '≤',
		contains: 'contains',
		starts_with: 'starts with',
		ends_with: 'ends with',
		in: 'is one of',
		not_in: 'is not one of',
		is_null: 'is empty',
		is_not_null: 'is set'
	};

	const STORE_CMP_OPS = ['lt', 'lte', 'eq', 'ne', 'gte', 'gt'];

	const NO_VALUE_OPS = new Set(['is_null', 'is_not_null']);
	const ARRAY_OPS = new Set(['in', 'not_in']);

	function fieldDef(name) {
		return fields.find((f) => f.name === name);
	}

	function defaultOp(fieldName) {
		const f = fieldDef(fieldName);
		if (!f) return 'eq';
		if (f.type === 'str') return 'contains';
		return 'eq';
	}

	function defaultValue(fieldName, op) {
		if (NO_VALUE_OPS.has(op)) return null;
		if (ARRAY_OPS.has(op)) return [];
		if (fieldName === 'store_id') return stores[0]?.id ?? '';
		const f = fieldDef(fieldName);
		if (!f) return '';
		if (f.type === 'bool') return true;
		return '';
	}

	function addCondition() {
		const field = fields[0]?.name ?? 'title';
		const op = defaultOp(field);
		group.conditions.push({
			type: 'condition',
			field,
			op,
			value: defaultValue(field, op)
		});
	}

	function addGroup() {
		group.conditions.push({ type: 'group', op: 'and', conditions: [] });
	}

	function addStoreCompare() {
		const a = stores[0]?.id ?? '';
		const b = stores[1]?.id ?? stores[0]?.id ?? '';
		group.conditions.push({
			type: 'store_compare',
			store_a: a,
			op: 'lt',
			store_b: b,
			value: 0,
			mode: 'abs'
		});
	}

	function storeName(id) {
		return stores.find((s) => s.id === id)?.name ?? id;
	}

	function storeCompareHint(cond) {
		const unit = cond.mode === 'pct' ? '%' : '';
		const v = Number(cond.value) || 0;
		const a = storeName(cond.store_a);
		const b = storeName(cond.store_b);
		if (v === 0) return `gap below 0 means cheaper at ${a}`;
		const size = `${Math.abs(v)}${unit}`;
		return v < 0
			? `e.g. ${size} cheaper at ${a} than ${b}`
			: `e.g. ${size} dearer at ${a} than ${b}`;
	}

	function removeChild(i) {
		group.conditions.splice(i, 1);
	}

	function onFieldChange(cond) {
		cond.op = defaultOp(cond.field);
		cond.value = defaultValue(cond.field, cond.op);
	}

	function onOpChange(cond) {
		cond.value = defaultValue(cond.field, cond.op);
	}

	function opsForField(fieldName) {
		return fieldDef(fieldName)?.ops ?? ['eq'];
	}

	function fieldType(fieldName) {
		return fieldDef(fieldName)?.type ?? 'str';
	}

	function arrayValueStr(v) {
		if (!v) return '';
		return Array.isArray(v) ? v.join(', ') : String(v);
	}

	function parseArrayValue(s) {
		return s
			.split(',')
			.map((x) => x.trim())
			.filter(Boolean);
	}
</script>

<div
	class="rounded-lg border {depth === 0
		? 'border-border bg-muted/30'
		: 'border-border/60 bg-background'} space-y-2 p-3"
>
	<!-- Group header -->
	<div class="flex items-center gap-2">
		<select bind:value={group.op} class="h-7 rounded border bg-background px-2 text-xs font-medium">
			<option value="and">ALL of (AND)</option>
			<option value="or">ANY of (OR)</option>
		</select>
		<span class="text-xs text-muted-foreground">the following match</span>
		{#if onremove}
			<button
				onclick={onremove}
				class="ml-auto rounded p-0.5 text-muted-foreground hover:bg-destructive/20 hover:text-destructive"
			>
				<X class="size-3.5" />
			</button>
		{/if}
	</div>

	<!-- Conditions -->
	{#each group.conditions as cond, i (i)}
		{#if cond.type === 'condition'}
			<div class="flex flex-wrap items-center gap-1.5 pl-2">
				<!-- Field -->
				<select
					bind:value={cond.field}
					onchange={() => onFieldChange(cond)}
					class="h-7 rounded border bg-background px-2 text-xs"
				>
					{#each fields as f}
						<option value={f.name}>{f.label}</option>
					{/each}
				</select>

				<!-- Operator -->
				<select
					bind:value={cond.op}
					onchange={() => onOpChange(cond)}
					class="h-7 rounded border bg-background px-2 text-xs"
				>
					{#each opsForField(cond.field) as op}
						<option value={op}>{OP_LABELS[op] ?? op}</option>
					{/each}
				</select>

				<!-- Value -->
				{#if !NO_VALUE_OPS.has(cond.op)}
					{#if cond.field === 'store_id' && ARRAY_OPS.has(cond.op)}
						<select
							multiple
							bind:value={cond.value}
							class="h-7 rounded border bg-background px-2 text-xs"
						>
							{#each stores as s}
								<option value={s.id}>{s.name}</option>
							{/each}
						</select>
					{:else if cond.field === 'store_id'}
						<select bind:value={cond.value} class="h-7 rounded border bg-background px-2 text-xs">
							{#each stores as s}
								<option value={s.id}>{s.name}</option>
							{/each}
						</select>
					{:else if fieldType(cond.field) === 'bool'}
						<select bind:value={cond.value} class="h-7 rounded border bg-background px-2 text-xs">
							<option value={true}>true</option>
							<option value={false}>false</option>
						</select>
					{:else if ARRAY_OPS.has(cond.op)}
						<input
							type="text"
							placeholder="val1, val2, …"
							value={arrayValueStr(cond.value)}
							oninput={(e) => (cond.value = parseArrayValue(e.target.value))}
							class="h-7 w-36 rounded border bg-background px-2 text-xs"
						/>
					{:else if fieldType(cond.field) === 'int' || fieldType(cond.field) === 'float'}
						<input
							type="number"
							bind:value={cond.value}
							step={fieldType(cond.field) === 'float' ? '0.5' : '1'}
							class="h-7 w-24 rounded border bg-background px-2 text-xs"
						/>
					{:else if fieldType(cond.field) === 'datetime'}
						<input
							type="date"
							bind:value={cond.value}
							class="h-7 rounded border bg-background px-2 text-xs"
						/>
					{:else}
						<!-- data-field: lets a shortcut jump straight to a condition's value. -->
						<input
							type="text"
							data-field={cond.field}
							bind:value={cond.value}
							class="h-7 w-36 rounded border bg-background px-2 text-xs"
						/>
					{/if}
				{/if}

				<button
					onclick={() => removeChild(i)}
					class="rounded p-0.5 text-muted-foreground hover:bg-destructive/20 hover:text-destructive"
				>
					<X class="size-3.5" />
				</button>
			</div>
		{:else if cond.type === 'store_compare'}
			<div class="flex flex-wrap items-center gap-1.5 pl-2">
				<!-- Store A -->
				<select bind:value={cond.store_a} class="h-7 rounded border bg-background px-2 text-xs">
					{#each stores as s}
						<option value={s.id}>{s.name}</option>
					{/each}
				</select>

				<span class="text-xs text-muted-foreground">−</span>

				<!-- Store B -->
				<select bind:value={cond.store_b} class="h-7 rounded border bg-background px-2 text-xs">
					{#each stores as s}
						<option value={s.id}>{s.name}</option>
					{/each}
				</select>

				<span class="text-xs text-muted-foreground">price gap</span>

				<!-- Operator -->
				<select bind:value={cond.op} class="h-7 rounded border bg-background px-2 text-xs">
					{#each STORE_CMP_OPS as op}
						<option value={op}>{OP_LABELS[op] ?? op}</option>
					{/each}
				</select>

				<!-- Threshold -->
				<input
					type="number"
					bind:value={cond.value}
					step="1"
					class="h-7 w-24 rounded border bg-background px-2 text-xs"
				/>

				<select bind:value={cond.mode} class="h-7 rounded border bg-background px-2 text-xs">
					<option value="abs">amount</option>
					<option value="pct">%</option>
				</select>

				<button
					onclick={() => removeChild(i)}
					class="rounded p-0.5 text-muted-foreground hover:bg-destructive/20 hover:text-destructive"
				>
					<X class="size-3.5" />
				</button>
			</div>
			<p class="pl-2 text-[11px] text-muted-foreground">
				{storeCompareHint(cond)}
			</p>
		{:else}
			<!-- Nested group (recursive) -->
			<div class="pl-2">
				<FilterGroup
					bind:group={group.conditions[i]}
					{fields}
					{stores}
					depth={depth + 1}
					onremove={() => removeChild(i)}
				/>
			</div>
		{/if}
	{/each}

	<!-- Add buttons -->
	<div class="flex gap-1.5 pt-1 pl-2">
		<button
			onclick={addCondition}
			class="flex items-center gap-1 rounded border px-2 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
		>
			<Plus class="size-3" /> condition
		</button>
		{#if stores.length >= 2}
			<button
				onclick={addStoreCompare}
				class="flex items-center gap-1 rounded border px-2 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
			>
				<ArrowLeftRight class="size-3" /> compare stores
			</button>
		{/if}
		{#if depth < 3}
			<button
				onclick={addGroup}
				class="flex items-center gap-1 rounded border px-2 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
			>
				<GitBranch class="size-3" /> group
			</button>
		{/if}
	</div>
</div>
