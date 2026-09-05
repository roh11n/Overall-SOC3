import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

export default function TimeTabs({ value, onChange }) {
  return (
    <Tabs value={value} onValueChange={onChange} data-testid="time-tabs">
      <TabsList className="grid grid-cols-3 w-full sm:w-[360px]">
        <TabsTrigger value="weekly" data-testid="tab-weekly">Weekly</TabsTrigger>
        <TabsTrigger value="monthly" data-testid="tab-monthly">Monthly</TabsTrigger>
        <TabsTrigger value="quarterly" data-testid="tab-quarterly">Quarterly</TabsTrigger>
      </TabsList>
    </Tabs>
  );
}
